# AI-image-classifier

Takes input of images of a given format and extracts the required data such as Dates, phone numbers, emails etc. Configurable through REGEX

## How to get started?

- Step 1:
  This project uses python 3.14. It is ideal to use a virtual environment like venv or conda for dependencies.
- Step 2:
  ensure you have cuda downloaded and setup.
  use `nvidia smi` to check the current version, this project uses cuda 13.x
  If your setup does not support cuda, you can refer to (CPU only environment)[]
- Step 3:
  run `pip install uv; uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130; uv pip install -r requirements.txt`
- Step 4:
  create a `.env` file with the following content:
  
```.env
whatsapp_groups= Group, or DM, Names, Here
```

- Step 5:
  configure your settings and run the program
