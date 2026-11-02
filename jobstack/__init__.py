"""jobstack: tag job-post text with the tools it names (Okta, Intune, Jamf, CrowdStrike...)."""

from .tagger import Tagger, html_to_text, load_dictionary

__all__ = ['Tagger', 'html_to_text', 'load_dictionary']
__version__ = '0.1.0'
