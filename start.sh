cd /home/gdupont/docker/frigate-commander
source ./.venv/bin/activate
#source /home/gdupont/docker/frigate-commander/.venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000
