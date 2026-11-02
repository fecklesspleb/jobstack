import pytest

from jobstack import Tagger, html_to_text, load_dictionary


def tags(t, text):
    return set(t.find(text))


# --- word boundaries -------------------------------------------------------

@pytest.mark.parametrize('text,expected', [
    ('Okta-based SSO', {'Okta'}),
    ('Experience with Intune', {'Microsoft Intune'}),
    ('AWS and Azure', {'AWS', 'Microsoft Azure'}),
    ('follow all laws ASAP', set()),                 # no AWS in "laws", no SAP in "ASAP"
    ('C# and C++', {'C#', 'C++'}),
    ('Node.js services', {'Node.js'}),
    ('Kubernetes (k8s)', {'Kubernetes'}),
    ('Oktaberfest party', set()),                     # glued letters: not Okta
    ('jamfpro_admin variable', set()),
    ('(CrowdStrike)', {'CrowdStrike'}),
])
def test_whole_word_matching(tagger, text, expected):
    assert tags(tagger, text) == expected


# --- aliases ---------------------------------------------------------------

@pytest.mark.parametrize('alias', ['Intune', 'Microsoft Intune', 'Microsoft Endpoint Manager', 'INTUNE'])
def test_intune_aliases(tagger, alias):
    assert tags(tagger, f'Manage {alias} policies') == {'Microsoft Intune'}


@pytest.mark.parametrize('alias,tag', [
    ('SCCM', 'Microsoft Configuration Manager (SCCM)'),
    ('MECM', 'Microsoft Configuration Manager (SCCM)'),
    ('Azure AD', 'Microsoft Entra ID'),
    ('Entra ID', 'Microsoft Entra ID'),
    ('Jamf Pro', 'Jamf'),
    ('CrowdStrike Falcon', 'CrowdStrike'),
    ('Golang', 'Go'),
])
def test_aliases_map_to_one_tag(tagger, alias, tag):
    assert tags(tagger, alias) == {tag}


def test_longest_match_wins(tagger):
    assert tags(tagger, 'Jira Service Management') == {'Jira Service Management'}
    assert tags(tagger, 'Okta Workflows') == {'Okta Workflows'}


def test_mentions_are_counted(tagger):
    assert tagger.find('Intune, intune and Microsoft Intune') == {'Microsoft Intune': 3}


# --- false-positive guards -------------------------------------------------

@pytest.mark.parametrize('text', ['slack time', 'zoom in on the details', 'a git of a day', 'go to the park',
                                   'take a notion', 'a swift reply'])
def test_everyday_words_need_capitals(tagger, text):
    assert tags(tagger, text) == set()


def test_case_sensitive_terms_match_with_capitals(tagger):
    assert tags(tagger, 'Slack, Zoom, Git and Swift') == {'Slack', 'Zoom', 'Git', 'Swift'}


def test_ambiguous_words_left_out(tagger):
    assert tags(tagger, 'Office in Palo Alto. Teams work in Box canyons. Oracle of Omaha.') == set()
    assert tags(tagger, 'Palo Alto Networks firewalls') == {'Palo Alto Networks'}


def test_ignore_in_phrase(tagger):
    assert tags(tagger, 'Ivanti Endpoint Manager') == {'Ivanti'}
    assert tags(tagger, 'Microsoft Endpoint Manager') == {'Microsoft Intune'}
    assert tags(tagger, 'Our office is in Salesforce Tower') == set()
    assert tags(tagger, 'Salesforce admin') == {'Salesforce'}


def test_customer_list_sentences_skipped(tagger):
    r = tagger.tag(text='Trusted by companies like Okta and CrowdStrike. You will run Intune.')
    assert r['tags'] == ['Microsoft Intune']


def test_investor_sentence_skipped(tagger):
    assert tagger.tag(text='Our investors include the founders of Okta.')['tags'] == []


def test_gated_tool_outside_requirements_dropped(tagger):
    assert tagger.tag(text='Say hi in our company Slack. Interviews happen over Zoom.')['tags'] == []


def test_gated_tool_next_to_requirement_phrase_counts(tagger):
    assert tagger.tag(text='You will administer Slack and Zoom for 300 people.')['tags'] == ['Slack', 'Zoom']


def test_gated_tool_in_requirements_section_counts(tagger):
    text = 'About the job\nYou join a small team.\nRequirements\nSlack Enterprise Grid\nZoom Rooms'
    assert set(tagger.tag(text=text)['tags']) == {'Slack', 'Zoom'}


def test_specific_product_not_gated(tagger):
    assert tagger.tag(text='We just installed Zoom Rooms in every office.')['tags'] == ['Zoom']


def test_requirements_section_ends_at_next_heading(tagger):
    text = 'Requirements:\nOkta\nBenefits:\nWe use Slack for everything.'
    assert tagger.tag(text=text)['tags'] == ['Okta']


def test_inline_requirements_label(tagger):
    assert set(tagger.tag(text='Requirements: Slack, Okta')['tags']) == {'Slack', 'Okta'}


def test_own_company_name_dropped(tagger):
    r = tagger.tag('Sales Engineer', 'Help customers roll out CrowdStrike on AWS.', company='CrowdStrike, Inc.')
    assert r['tags'] == ['AWS']


def test_title_always_counts(tagger):
    r = tagger.tag('Okta Administrator', 'Join us.')
    assert r['tags'] == ['Okta'] and r['categories'] == ['identity']


def test_result_sorted_by_mentions(tagger):
    r = tagger.tag(text='Okta, Okta, Okta and Jamf, Jamf and Intune.')
    assert r['tags'] == ['Okta', 'Jamf', 'Microsoft Intune']
    assert r['mentions'] == {'Okta': 3, 'Jamf': 2, 'Microsoft Intune': 1}


def test_empty_input(tagger):
    assert tagger.tag() == {'tags': [], 'categories': [], 'mentions': {}}
    assert tagger.find(None) == {}


# --- custom terms and dictionary ------------------------------------------

def test_custom_terms():
    t = Tagger.default()
    t.add_terms(['Rippling', 'Kolide=Kolide|1Password Extended Access Management'])
    assert tags(t, 'Rippling and 1Password Extended Access Management') == {'Rippling', 'Kolide'}
    assert t.category['Rippling'] == 'custom'


def test_custom_dictionary_file(tmp_path):
    p = tmp_path / 'd.json'
    p.write_text('{"entries": [{"tag": "Widget", "category": "x", "aliases": ["widgetctl"], "caseSensitive": []}]}')
    t = Tagger.from_file(p)
    assert t.size == 1 and tags(t, 'use widgetctl') == {'Widget'}


def test_duplicate_tag_rejected(tmp_path):
    p = tmp_path / 'd.json'
    p.write_text('{"entries": [{"tag": "A", "aliases": ["a1"]}, {"tag": "A", "aliases": ["a2"]}]}')
    with pytest.raises(ValueError):
        load_dictionary(p)


def test_bundled_dictionary_is_valid():
    d = load_dictionary()
    assert d['license'] == 'MIT'
    assert len(d['entries']) >= 300
    for e in d['entries']:
        assert e['category'] and (e['aliases'] or e['caseSensitive'])
        for g in e.get('gated', []):
            assert g in e['aliases'] + e['caseSensitive']


@pytest.mark.parametrize('tag', ['Okta', 'Microsoft Intune', 'Jamf', 'CrowdStrike', 'Kandji',
                                 'SentinelOne', 'Microsoft Entra ID', 'ServiceNow'])
def test_core_it_tools_present(tagger, tag):
    assert tag in tagger.category


# --- HTML ------------------------------------------------------------------

def test_html_to_text_keeps_lines():
    assert html_to_text('<h3>Requirements</h3><ul><li>Okta</li><li>Intune</li></ul>') == 'Requirements\nOkta\nIntune'


def test_html_to_text_unescapes_greenhouse_content():
    assert html_to_text('&lt;p&gt;Jamf &amp;amp; Kandji&lt;/p&gt;') == 'Jamf & Kandji'


def test_html_to_text_empty():
    assert html_to_text(None) == ''


def test_benefits_heading_ends_requirements(tagger):
    text = 'Requirements\nOkta\nBenefits\nChat with us on Slack.'
    assert tagger.tag(text=text)['tags'] == ['Okta']
