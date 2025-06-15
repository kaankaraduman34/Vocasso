from openai import OpenAI
import PIL.Image,os,requests
from io import BytesIO
from datetime import datetime

client=None
def set_OpenAI_api_key(api_key):
    global client
    client = OpenAI(api_key=api_key)
    return client

def generate_image(promt,client):
    result = client.images.generate(
        model="dall-e-3",
        prompt=promt,
        size="1024x1024",
        response_format="url",
        n=1,
        quality="hd"
    )

    image_url = result.data[0].url

    response = requests.get(image_url)
    image_bytes = BytesIO(response.content)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"./img/generated_image_{timestamp}.png"

    if not os.path.exists("./img"):
        os.makedirs("./img")
    with open(filename, "wb") as f:
        f.write(image_bytes.getbuffer())

    return filename
