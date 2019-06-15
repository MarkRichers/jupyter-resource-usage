import os
import json
from traitlets import Float, Int, default
from traitlets.config import Configurable
from notebook.utils import url_path_join
from notebook.base.handlers import IPythonHandler
from tornado import web, iostream
import asyncio
import pluggy
from nbresuse import hooks, memory
from collections import ChainMap


plugin_manager = pluggy.PluginManager('nbresuse')
plugin_manager.add_hookspecs(hooks)
plugin_manager.register(memory)


class MetricsHandler(IPythonHandler):
    def initialize(self):
        self.set_header('content-type', 'text/event-stream')
        self.set_header('cache-control', 'no-cache')

    @web.authenticated
    async def get(self):
        """
        Calculate and return current resource usage metrics
        """
        config = self.settings['nbresuse_display_config']
        while True:
            metrics = {}
            for metric_response in plugin_manager.hook.nbresuse_add_resource(config=config):
                metrics.update(metric_response)
            self.write('data: {}\n\n'.format(json.dumps(metrics)))
            try:
                await self.flush()
            except iostream.StreamClosedError:
                return
            await asyncio.sleep(5)


def _jupyter_server_extension_paths():
    """
    Set up the server extension for collecting metrics
    """
    return [{
        'module': 'nbresuse',
    }]

def _jupyter_nbextension_paths():
    """
    Set up the notebook extension for displaying metrics
    """
    return [{
        "section": "notebook",
        "dest": "nbresuse",
        "src": "static",
        "require": "nbresuse/main"
    }]

class ResourceUseDisplay(Configurable):
    """
    Holds server-side configuration for nbresuse
    """

    mem_warning_threshold = Float(
        0.1,
        help="""
        Warn user with flashing lights when memory usage is within this fraction
        memory limit.

        For example, if memory limit is 128MB, `mem_warning_threshold` is 0.1,
        we will start warning the user when they use (128 - (128 * 0.1)) MB.

        Set to 0 to disable warning.
        """,
        config=True
    )

    mem_limit = Int(
        0,
        config=True,
        help="""
        Memory limit to display to the user, in bytes.

        Note that this does not actually limit the user's memory usage!

        Defaults to reading from the `MEM_LIMIT` environment variable. If
        set to 0, no memory limit is displayed.
        """
    )

    @default('mem_limit')
    def _mem_limit_default(self):
        return int(os.environ.get('MEM_LIMIT', 0))

def load_jupyter_server_extension(nbapp):
    """
    Called during notebook start
    """
    resuseconfig = ResourceUseDisplay(parent=nbapp)
    nbapp.web_app.settings['nbresuse_display_config'] = resuseconfig
    route_pattern = url_path_join(nbapp.web_app.settings['base_url'], '/api/nbresuse')
    nbapp.web_app.add_handlers('.*', [(route_pattern, MetricsHandler)])
