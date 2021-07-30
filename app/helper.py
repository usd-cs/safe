from pygments import highlight
from pygments.lexers import get_lexer_for_filename
from pygments.formatters import HtmlFormatter
import pygments.util

from flask import Markup

def get_formatted_file_contents(target_file):
    try:
        lexer = get_lexer_for_filename(target_file.filename)
        formatted_file = Markup(highlight(target_file.data,
                                            lexer,
                                            HtmlFormatter(linenos=True)))
    except pygments.util.ClassNotFound:
        formatted_file = "Viewing this type of file is unsupported."

    return formatted_file

