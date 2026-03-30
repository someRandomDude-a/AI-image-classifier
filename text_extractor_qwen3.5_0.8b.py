import torch
from transformers import AutoProcessor, AutoModelForImageTextToText
from qwen_vl_utils import process_vision_info
from PIL import Image
from pathlib import Path
import warnings
import re

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

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

_MAX_NEW_TOKENS = 64

def clean_json_output(text: str) -> str:
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```", "", text)
    return text.strip()

def extract_image(image: str | Image.Image | Path, prompt: str = 'Extract {"order_id": "", "order_date": ""} from this image. Return JSON only.') -> str:
    """
    Extracts text from a given image path or Image object and an optional prompt
    Returns model output as a string
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

    image_inputs, _ = process_vision_info(messages)

    inputs = processor(
        text=[text],
        images=image_inputs,
        return_tensors="pt"
    ).to(model.device)

    with torch.inference_mode():
        output = model.generate(
            **inputs, max_new_tokens=_MAX_NEW_TOKENS,
            pad_token_id=model.config.pad_token_id,
            eos_token_id=model.config.eos_token_id
            )

    result = processor.batch_decode(
        output[:, inputs.input_ids.shape[-1]:],
        skip_special_tokens=True
    )

    return clean_json_output(result[0])

def estimate_image_peak_mem(image_path: Path, prompt: str) -> tuple[int, str]:
    """
    Estimates peak memory for a single image, returns (peak_mem_in_bytes, result)
    Works for both CPU (psutil) and GPU
    """
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats(model.device)
        result = extract_image(image_path, prompt)
        peak_mem = torch.cuda.max_memory_allocated(model.device)

    elif _PSUTIL:
        process = psutil.Process()
        mem_before = process.memory_info().rss
        result = extract_image(image_path, prompt)
        mem_after = process.memory_info().rss
        peak_mem = mem_after - mem_before

    else:
        result = extract_image(image_path, prompt)
        peak_mem = 1e9  # fallback ~1GB

    return peak_mem, result

def compute_batch_size(image_path: Path, prompt: str, safety_factor: float = 0.8) -> int:
    peak_mem, result = estimate_image_peak_mem(image_path, prompt)
    if torch.cuda.is_available():
        free_mem = torch.cuda.mem_get_info()[0]
    elif _PSUTIL:
        free_mem = psutil.virtual_memory().available
    else:
        warnings.warn(
            "psutil not installed and cuda is not available, "
            "it is likely you are unintentionally using the CPU. "
            "unable to estimate available ram, assuming 1gb!",
            UserWarning
            )
        free_mem = 1e9 

    batch_size = max(1, int(free_mem * safety_factor / peak_mem))
    return batch_size, result

def batch_extract_image(images: list[Path], prompt: str = 'Extract {"order_id": "", "order_date": ""} from this image. Return JSON only.') -> list[str]:
    """
    Extracts text from a list of Path objects with automatic batching
    Returns a list of strings, preserving the order of the input list
    """

    if not images:
        return []

    batch_size, first_result = compute_batch_size(images[0], prompt)
    results = [first_result]

    for i in range(1, len(images), batch_size):
        batch = images[i:i+batch_size]
        for image_path in batch:
            image = Image.open(image_path)
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            image_inputs, _ = process_vision_info(messages)
            inputs = processor(text=[text], images=image_inputs, return_tensors="pt").to(model.device)

            with torch.inference_mode():
                output = model.generate(
                    **inputs,
                    max_new_tokens=_MAX_NEW_TOKENS,
                    pad_token_id=model.config.pad_token_id,
                    eos_token_id=model.config.eos_token_id
                )

            decoded = processor.batch_decode(
                output[:, inputs.input_ids.shape[-1]:],
                skip_special_tokens=True
            )[0]

            results.append(clean_json_output(decoded))

    return results

if __name__ == "__main__":
    directory = Path("./Images")
    pictures = sorted(directory.iterdir())
    for picture in pictures:
        print(extract_image(picture))
    print("\n\nTesting Batch Mode!\n\n")
    results = batch_extract_image(pictures)
    for result in results:
        print(result)
