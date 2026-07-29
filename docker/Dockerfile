# Use Miniconda as the base image
FROM anaconda/miniconda:latest

# Set working directory
WORKDIR /app

# Copy the environment file into the container.
# NOTE: the build context is the repo root (see docker-compose.yml), so paths
# are relative to the repository root rather than this docker/ directory.
COPY docker/environment.yaml .

# Accept Anaconda Terms of Service
ENV CONDA_PLUGINS_AUTO_ACCEPT_TOS=true

# Create the conda environment from the YAML file
RUN conda env create -f environment.yaml -n janusgraph_env

# Make janusgraph_env the default (no conda activate needed)
ENV PATH=/opt/miniconda3/envs/janusgraph_env/bin:$PATH

# Force Docker to use bash as a login shell
SHELL ["/bin/bash", "--login", "-c"]

RUN conda init bash

RUN conda activate janusgraph_env

# Install zsh and oh-my-zsh with Soliah theme
RUN apt-get update && apt-get install -y zsh curl git && \
    sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended && \
    sed -i 's/ZSH_THEME="robbyrussell"/ZSH_THEME="Soliah"/' ~/.zshrc

# Set zsh as default shell
SHELL ["/bin/zsh", "-c"]
CMD ["zsh"]

# --- document-server application code -----------------------------------------
# Copied last so editing app source does not invalidate the (slow) conda layer.
# The janusgraph_env conda env already provides flask/pymongo/gunicorn.
# The source tree is copied under /app/src so the package is importable as
# `visualizer.document_server` (gunicorn visualizer.document_server.wsgi:app).
COPY src /app/src

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    MONGO_URI=mongodb://mongo:27017

# Each service in docker-compose.yml supplies its own `command`
# (document-server -> gunicorn; janusgraph app -> sleep infinity).