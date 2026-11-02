import json

from jobstack.cli import main


def test_cli_tag_text(capsys):
    assert main(['tag', 'Requirements: Okta, Intune and Jamf']) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out['tags']) == {'Okta', 'Microsoft Intune', 'Jamf'}


def test_cli_tag_custom_term(capsys):
    main(['tag', 'We run Rippling for HR', '--term', 'Rippling'])
    assert json.loads(capsys.readouterr().out)['tags'] == ['Rippling']


def test_cli_company_flag(capsys):
    main(['tag', 'Deploy Jamf Pro to customers', '--company', 'Jamf'])
    assert json.loads(capsys.readouterr().out)['tags'] == []
