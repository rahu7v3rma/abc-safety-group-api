import base64
import re
from typing import Union

from PIL import ExifTags, Image, ImageOps
from pyppeteer import launch

from src import log

allowed_sizes = [16, 24, 60, 300, 600, 1024]


def is_valid_image(file_path) -> bool:
    """Function to detect whether or not the image is a valid image

    Args:
        file_path (_type_): File path to image

    Returns:
        bool: Bool whether or not the image is valid
    """
    try:
        with Image.open(file_path) as img:
            return img.format is not None
    except Exception:
        return False


def resize_image(image_path: str, size: int = 300) -> Union[str, Image.Image]:
    """Function to resize an image

    Args:
        image_path (str): Path to image
        size (int, optional): Size to resize the image to. Defaults to 300.
        Allowed image sizes [16, 24, 60, 300, 600, 1024]
    Raises:
        e: error for image resizing

    Returns:
        Union[str, Image.Image]: Returns image or str for error
    """
    image = Image.open(image_path)
    image = ImageOps.exif_transpose(image)
    orientation = 0
    for tag, value in image.getexif().items():
        if ExifTags.TAGS.get(tag) == "Orientation":
            orientation = value
            break

    if orientation == 3:
        image = image.rotate(180, expand=True)
    elif orientation == 6:
        image = image.rotate(270, expand=True)
    elif orientation == 8:
        image = image.rotate(90, expand=True)

    if size not in allowed_sizes:
        return f"{size} is not a valid size"

    try:
        image.thumbnail((size, size), Image.LANCZOS)

    except Exception as e:
        log.exception("An exception occured while resizing image")
        raise e

    return image


def read_and_encode_image(file_path) -> str:
    with open(file_path, "rb") as image_file:
        image_data = image_file.read()

    base64_image = base64.b64encode(image_data).decode()
    return base64_image


async def html_to_png(html_content, output_path) -> Union[str, bytes]:
    try:
        browser = await launch(
            executablePath="/usr/bin/google-chrome-stable",
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-software-rasterizer",
                "--single-process",
                "--disable-dev-shm-usage",
                "--no-zygote",
            ],
        )
        page = await browser.newPage()
        await page.setViewport({"width": 1300, "height": 1000})
        pattern = r'src="([a-z0-9/._]+)"'

        def replace_src(match) -> str:
            src = match.group(1)
            src_path = f"/source/src/content/certificates{src[1:]}"

            base64_image = read_and_encode_image(src_path)

            return f'src="data:image/jpeg;base64,{base64_image}"'

        modified_html = re.sub(pattern, replace_src, html_content)

        await page.setContent(modified_html)
        await page.addStyleTag(
            path="/source/src/content/certificates/styles/output.css",
        )
        await page.waitFor(500)
        screenshot = await page.screenshot()
        await browser.close()

        return screenshot

    except Exception as e:
        raise e
