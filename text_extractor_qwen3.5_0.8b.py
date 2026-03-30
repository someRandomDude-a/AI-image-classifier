import torch
from transformers import AutoProcessor, AutoModelForImageTextToText
from qwen_vl_utils import process_vision_info
from PIL import Image
from pathlib import Path
import warnings
import re
from concurrent.futures import ThreadPoolExecutor

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
tokenizer.padding_side = "left"
model.config.pad_token_id = tokenizer.pad_token_id
model.config.eos_token_id = tokenizer.eos_token_id

model.eval()

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
    Estimates peak memory for a single image relative to current GPU usage.
    Returns (peak_mem_in_bytes, result)
    """
    if torch.cuda.is_available():
        device = model.device
        mem_before = torch.cuda.memory_allocated(device)
        torch.cuda.reset_peak_memory_stats(device)  

        result = extract_image(image_path, prompt)

        peak_mem = torch.cuda.max_memory_allocated(device)
        peak_mem_delta = peak_mem - mem_before

    elif _PSUTIL:
        process = psutil.Process()
        mem_before = process.memory_info().rss
        result = extract_image(image_path, prompt)
        mem_after = process.memory_info().rss
        peak_mem_delta = mem_after - mem_before

    else:
        result = extract_image(image_path, prompt)
        peak_mem_delta = 1e9  # fallback ~1GB

    peak_mem_delta = max(int(peak_mem_delta), 1_000_000)
    return peak_mem_delta, result

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

def apply_template(msg):
    return processor.apply_chat_template(
        msg,
        tokenize=False,
        add_generation_prompt=True
    )
def load_image(path):
    with Image.open(path) as img:
        return img.copy()
def batch_extract_image_prefetch(images: list[Path], prompt: str = 'Extract {"order_id": "", "order_date": ""} from this image. Return JSON only.', prefetch_batches: int = 2):
    """
    Generator version of batch extraction with prefetching.
    Prepares up to `prefetch_batches` ahead while GPU is generating the current batch.
    """
    from queue import Queue
    from threading import Thread

    images = [p for p in images if p.suffix.lower() in [".png", ".jpg", ".jpeg"]]
    if not images:
        return

    batch_size, first_result = compute_batch_size(images[0], prompt)
    yield first_result

    batch_queue = Queue(maxsize=prefetch_batches)

    def prepare_batch(batch_paths):
        """Load images and apply template in parallel"""
        with ThreadPoolExecutor(max_workers=8) as executor:
            
            pil_images = list(executor.map(load_image, batch_paths))

            messages_batch = [
                [{
                    "role": "user",
                    "content": [
                        {"type": "image", "image": img},
                        {"type": "text", "text": prompt}
                    ]
                }]
                for img in pil_images
            ]

            texts = list(executor.map(apply_template, messages_batch))

        image_inputs, _ = process_vision_info(messages_batch)
        inputs = processor(
            text=texts,
            images=image_inputs,
            return_tensors="pt",
            padding=True
        ).to(model.device)

        return inputs

    def prefetch_worker():
        for i in range(1, len(images), batch_size):
            batch_paths = images[i:i+batch_size]
            inputs = prepare_batch(batch_paths)
            batch_queue.put(inputs)
        # signal the end
        batch_queue.put(None)

    thread = Thread(target=prefetch_worker, daemon=True)
    thread.start()

    while True:
        inputs = batch_queue.get()
        if inputs is None:
            break

        with torch.inference_mode():
            outputs = model.generate(
                **inputs,
                max_new_tokens=_MAX_NEW_TOKENS,
                pad_token_id=model.config.pad_token_id,
                eos_token_id=model.config.eos_token_id
            )

        decoded = processor.batch_decode(
            outputs[:, inputs.input_ids.shape[-1]:],
            skip_special_tokens=True
        )

        for d in decoded:
            yield clean_json_output(d)

if __name__ == "__main__":
    directory = Path("./Images")
    pictures = sorted(directory.iterdir())
    # for picture in pictures:
    #    print(extract_image(picture))

    print("\n\nTesting Prefetch Batch Mode!\n\n")

    for result in batch_extract_image_prefetch(pictures):
        print(result)