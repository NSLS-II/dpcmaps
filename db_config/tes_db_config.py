import h5py

try:
    from databroker.v0 import Broker
except ModuleNotFoundError:
    from databroker import Broker

from databroker._core import register_builtin_handlers

#  srx detector, to be moved to filestore
# from databroker.assets.handlers import Xspress3HDF5Handler
from databroker.assets.handlers import HandlerBase

import logging

logger = logging.getLogger(__name__)

db = Broker.named("tes")
try:
    register_builtin_handlers(db.reg)
except Exception as ex:
    logger.error(f"Error while registering default SRX handlers: {ex}")


class BulkXSPRESS(HandlerBase):
    HANDLER_NAME = "XPS3_FLY"

    def __init__(self, resource_fn):
        self._handle = h5py.File(resource_fn, "r")

    def __call__(self):
        return self._handle["entry/instrument/detector/data"][:]


db.reg.register_handler(BulkXSPRESS.HANDLER_NAME, BulkXSPRESS, overwrite=True)
