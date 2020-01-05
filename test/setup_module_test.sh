#!/usr/bin/env bash
set -e
set -xv

THIS_PATH=$(dirname "$0")
BASE_PATH=$(dirname "$THIS_PATH")

cd $BASE_PATH

echo 'Upgrade pip ...'
pip install --upgrade pip

# Module name
name=graphite
echo "Module name: $name"

# Python version
py_version_short=$(python -c "import sys; print(''.join(str(x) for x in sys.version_info[:2]))")
# -> 27 or 34 or ..
echo "Python version: $py_version_short"

# Clone and configure Shinken
SHI_DST=test/tmp/shinken
# Extend the test configurations with the modules one
if [ -d "$SHI_DST" ]
then
   echo "Shinken is still cloned"
else
   git clone --depth 10 https://github.com/naparuba/shinken.git "$SHI_DST"
fi
( cd "$SHI_DST" && git status && git log -1)

echo 'Installing Shinken tests requirements...'
(
    cd "$SHI_DST"
    pip install -r test/requirements.txt
    if [ -f "test/${spec_requirement}" ]
    then
        pip install -r "test/${spec_requirement}"
    fi
)

echo 'Installing tests requirements + application requirements...'
pip install --upgrade -r test/requirements.txt
if [ -f "test/requirements.py${py_version_short}.txt" ]
then
    pip install -r "test/requirements.py${py_version_short}.txt"
fi

# Map module directory to the Shinken test modules directory
if [ ! -d "$SHI_DST/test/modules/$name" ]
then
   ln -s "$PWD/module" "$SHI_DST/test/modules/$name"
fi
