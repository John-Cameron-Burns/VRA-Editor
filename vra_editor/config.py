import configparser, psutil
import logging
from functools import reduce
from pathlib import Path

from .utils import get_full_name


config = configparser.ConfigParser()
# Create a ConfigParser instance
def _get_config():
    filename = Path('~/vra-config.ini').absolute()
    if   filename.exists():
        # Read the INI file
        config.read(str(filename))
    else:
        logging.warning(f"Config file not found: {filename}")
        config.add_section('locations')
        config.set('locations','edit','' )
        config.set('locations', 'ingest', '')
        config.set('locations', 'pending', '')
        config.set('locations', 'rejected', '')
        config.set('locations', 'reviewed', '')
        config.set('locations', 'released', '')

        config.add_section('user')
        config.set('user', 'FullName', get_full_name())

        config.add_section('options')
        config.set('options', 'auto_ingest', True)
        config.set('options', 'image_pattern', 'i_*.xml')
        config.set('options', 'collection_pattern', 'w_*.xml')

        config.write(open(filename, 'wt'))

        # todo - auto open config page on first run

