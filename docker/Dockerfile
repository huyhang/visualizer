# Use Miniconda as the base image
FROM anaconda/miniconda:latest

# Set working directory
WORKDIR /app

# Copy the environment file into the container
COPY environment.yaml .

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
    sed -i 's/ZSH_THEME="robbyrussell"/ZSH_THEME="soliah"/' ~/.zshrc

# Set zsh as default shell
SHELL ["/bin/zsh", "-c"]
CMD ["zsh"]

# Doing nothing for now, but necessary so that we have a live docker container for testing
CMD ["sleep", "infinity"]