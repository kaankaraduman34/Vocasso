from openai import OpenAI

client=None
def set_OpenAI_api_key(api_key):
    global client
    client = OpenAI(api_key=api_key)
    return client

def transcribe(audio_file,client,languages="tr"):

    audio_file = open(audio_file,'rb')
    AI_generated = client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=audio_file,
        language=languages
    )
    return AI_generated.text

