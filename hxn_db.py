

from hxntools.handlers import register
import filestore
register()

import yaml
with open("/home/xf03id/.config/databroker/hxn.yml","r") as read_file:
    data=yaml.load(read_file)

from metadatastore.mds import MDS
from databroker import Broker
from databroker.core import register_builtin_handlers
from filestore.fs import FileStore

_mds_config = {'host': data['metadatastore']['config']['host'],
               'port': 27017,
               'database': data['metadatastore']['config']['database'],
               'timezone': 'US/Eastern'}
mds = MDS(_mds_config)
_fs_config = {'host': data['assets']['config']['host'],
              'port': 27017,
              'database': data['assets']['config']['database']}
db = Broker(mds, FileStore(_fs_config))

from hxntools.handlers.timepix import TimepixHDF5Handler
from hxntools.handlers.xspress3 import Xspress3HDF5Handler
db.fs.register_handler(TimepixHDF5Handler._handler_name, TimepixHDF5Handler, overwrite=True)


