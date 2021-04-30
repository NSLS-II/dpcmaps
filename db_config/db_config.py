import json

beamline_name = ""

# The following code is borrowed from PyXRF. It supposed to determine beamline name
#   based on PyXRF configuration file '/etc/pyxrf/pyxrf.json'
try:
    config_path = "/etc/pyxrf/pyxrf.json"
    with open(config_path, "r") as beamline_pyxrf:
        beamline_config_pyxrf = json.load(beamline_pyxrf)
        beamline_name = beamline_config_pyxrf["beamline_name"]
    if beamline_name == "HXN":
        from .hxn_db_config import db
    elif beamline_name == "SRX":
        from .srx_db_config import db
    elif beamline_name == "XFM":
        from .xfm_db_config import db
    elif beamline_name == "TES":
        from .tes_db_config import db
    else:
        db = None
except IOError:
    db = None
    print("Beamline Database is not used.")
