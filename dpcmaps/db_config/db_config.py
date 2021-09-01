import json
import os
import platform

beamline_name = ""

# The following code is borrowed from PyXRF. It supposed to determine beamline name
#   based on PyXRF configuration file '/etc/pyxrf/pyxrf.json'

try:
    beamline_name = ""

    # Attempt to find the configuration file first
    config_path = "/etc/pyxrf/pyxrf.json"
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r") as beamline_pyxrf:
                beamline_config_pyxrf = json.load(beamline_pyxrf)
                beamline_name = beamline_config_pyxrf["beamline_name"]
        except Exception as ex:
            raise IOError(f"Error while opening configuration file {config_path!r}") from ex

    else:
        # Otherwise try to identify the beamline using host name
        hostname = platform.node()
        beamline_names = {
            "xf03id": "HXN",
            "xf05id": "SRX",
            "xf08bm": "TES",
            "xf04bm": "XFM",
        }

        for k, v in beamline_names.items():
            if hostname.startswith(k):
                beamline_name = v

    if not beamline_name:
        raise Exception("Beamline is not identified")

    if beamline_name == "HXN":
        from pyxrf.db_config.hxn_db_config import db
    # elif beamline_name == "SRX":
    #     from pyxrf.db_config.srx_db_config import db
    # elif beamline_name == "XFM":
    #     from pyxrf.db_config.xfm_db_config import db
    # elif beamline_name == "TES":
    #     from pyxrf.db_config.tes_db_config import db
    else:
        db = None
        db_analysis = None
        print(f"Beamline Database is not used in pyxrf: beamline {beamline_name!r} is not supported")

except Exception as ex:
    db = None
    print(f"Beamline Database is not used in pyxrf: {ex}")
