import torch
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
from PIL import Image
from pathlib import Path

model_id = "Qwen/Qwen3-VL-2B-Instruct"

model = Qwen3VLForConditionalGeneration.from_pretrained(
    model_id,
    device_map="auto",
    dtype=torch.float16 if torch.cuda.is_available() else torch.float32  # Use float16 for GPU and float32 for CPU
    )

model.eval()
processor = AutoProcessor.from_pretrained(model_id)
model = torch.compile(model)

def extract_image(image: str | Image.Image | Path, prompt: str = 'Extract {"order_id": "", "order_date": ""} from this image. Return JSON only.') -> str:
    """
    Extracts text from a given image path or Image object and an optional prompt
    Returns model output as string
    """

    image = Image.open(image) if isinstance(image, (str, Path)) else image

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
    )

    inputs = inputs.to(model.device)

    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=128)

    result = processor.batch_decode(
        output[:, inputs.input_ids.shape[-1]:],
        skip_special_tokens=True
    )

    return result[0]

if __name__ == "__main__":

    directory = Path("./Images")
    for picture in sorted(directory.iterdir()):
        print(extract_image(picture))
