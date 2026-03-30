import torch
from transformers import AutoProcessor, AutoModelForImageTextToText
from qwen_vl_utils import process_vision_info
from PIL import Image
from pathlib import Path

model_id = "Qwen/Qwen3.5-0.8B"
model = AutoModelForImageTextToText.from_pretrained(
    model_id,
    device_map="auto",
    dtype=torch.float16 if torch.cuda.is_available() else torch.float32
    )

processor = AutoProcessor.from_pretrained(model_id)

tokenizer = processor.tokenizer
model.config.pad_token_id = tokenizer.pad_token_id
model.config.eos_token_id = tokenizer.eos_token_id

model.eval()
model = torch.compile(model)

def extract_image(image: str | Image.Image | Path, prompt: str = 'Extract {"order_id": "", "order_date": ""} from this image. Return JSON only.') -> str:
    """
    Extracts text from a given image path or Image object and an optional prompt
    Returns model output as a string
    """

    # Ensure the image is in the correct format
    image = Image.open(image) if isinstance(image, (str, Path)) else image

    # Prepare the message format for the model
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt}
            ]
        }
    ]

    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    image_inputs, video_inputs = process_vision_info(messages)

    inputs = processor(
        text=[text],
        images=image_inputs,
        return_tensors="pt"
    ).to(model.device)

    with torch.inference_mode():
        output = model.generate(
            **inputs, max_new_tokens=64,
            pad_token_id=model.config.pad_token_id,
            eos_token_id=model.config.eos_token_id
            )

    result = processor.batch_decode(
        output[:, inputs.input_ids.shape[-1]:],
        skip_special_tokens=True
    )

    return result[0]

def batch_extract_image(image: list[Path],prompt: str = 'Extract {"order_id": "", "order_date": ""} from this image. Return JSON only.') -> list[str]:
    """
    Extracts text from a given list of Pathlib.Path objects and an optional prompt
    Returns model output as list of Strings
    """
    pass

if __name__ == "__main__":
    directory = Path("./Images")
    for picture in sorted(directory.iterdir()):
        print(extract_image(picture))