import json
from pathlib import Path

import pytest

from jobstack import Tagger

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture(scope='session')
def tagger():
    return Tagger.default()


@pytest.fixture
def fixture_json():
    return lambda name: json.loads((FIXTURES / name).read_text(encoding='utf-8'))
