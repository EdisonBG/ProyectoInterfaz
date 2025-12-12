#!/bin/bash
set -e

echo "Entrando a la carpeta del proyecto..."
cd /home/eia/Desktop/.ProyectoInterfaz

echo "Activando entorno virtual..."
source /home/eia/Desktop/.ProyectoInterfaz/.venv/bin/activate


echo "Ejecutando programa..."
python3 main.py

echo
echo "El programa termino. Si ves un error revisalo"

