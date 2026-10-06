# Restaurador Fotográfico para Fedora

Aplicación gráfica en español para mejorar fotografías mediante procesamiento
clásico local. Incluye Python 3.14, OpenCV, NumPy, Pillow y los componentes de Qt
necesarios. No requiere internet, cuentas, claves API, modelos ni una GPU.

## Instalar

También se entrega `Restaurador_Fotografico`, un ejecutable nativo de Linux
que contiene el paquete completo. Puedes abrirlo directamente con doble clic
en Dolphin, o ejecutar `./Restaurador_Fotografico` desde su carpeta. Extrae las
dependencias a una carpeta temporal y las limpia cuando cierras la aplicación.
Requiere las herramientas base `tar` y `rm` de Fedora y unos 400 MB libres en
`/tmp`. Para instalar desde ese ejecutable usa `./Restaurador_Fotografico --instalar`.
Para comprobarlo usa `./Restaurador_Fotografico --verificar`.

Paquete preparado y probado en Fedora 44 x86_64. Requiere un escritorio gráfico
y las bibliotecas base de Fedora 44 (glibc). No se garantiza compatibilidad con
distribuciones anteriores ni otras arquitecturas.

Si recibiste el instalador de un solo archivo, ejecuta:

```bash
bash Restaurador_Fotografico_Fedora_1.0.0.run
```

Este instalador extrae una copia temporal, verifica el programa, lo instala
para tu usuario y limpia sus archivos temporales. No descarga nada.

Extrae el archivo `.tar.gz` y ejecuta desde la carpeta extraída:

```bash
bash instalar.sh
```

Instala para tu usuario en `~/.local/share/restaurador-fotografico` y agrega
Restaurador Fotográfico al menú de aplicaciones. No requiere sudo.

También puedes usarla sin instalar:

```bash
bash abrir.sh
```

Para verificar las dependencias, el motor y la interfaz sin pantalla:

```bash
bash abrir.sh --verificar
```

## Uso

1. Abre una imagen PNG, JPEG, TIFF, BMP o WebP.
2. Elige Acabado actual, Restauración suave, Foto deteriorada o Sin ajustes.
3. Ajusta color, ruido, contraste por zonas, sombras, brillo, saturación y nitidez.
4. Para corregir un dominante de color, elige Blanco y pulsa sobre una zona
   que debería ser blanca o gris. Evita brillos quemados y zonas de color.
5. Para reparar pequeñas motas o arañazos, elige Reparar y pinta sobre ellos
   en la vista original. Las marcas naranjas indican la máscara. Limpiar blanco
   y marcas borra la selección. No uses este pincel para reconstruir áreas grandes.
6. Elige recorte inferior si deseas quitar una franja del borde y ampliación 1×,
   2× o 3×. La ampliación usa interpolación y no reconstruye detalles con IA.
7. Pulsa Aplicar mejora y compara las dos vistas. El procesamiento trabaja en
   segundo plano. Al cambiar controles, vuelve a aplicar antes de guardar.
8. Guarda con un nombre nuevo en PNG o JPEG. El archivo original está protegido.
   Si eliges otro archivo existente, el diálogo del escritorio pide confirmar
   su reemplazo. La exportación se verifica antes de completar la escritura.

Ctrl+O abre una foto; Ctrl+Shift+S guarda el resultado. Los ajustes pueden
exportarse a JSON como registro; ese archivo no incluye las marcas del pincel
y esta versión no importa recetas.

El balance automático es una estimación y puede necesitar selección manual
de blanco. El ruido alto puede suavizar piel y pelo; empieza con valores bajos.
Los límites son 24 megapíxeles de entrada y 36 megapíxeles de salida. El tiempo
de procesamiento depende de la resolución y CPU. No se promete convertir una
foto pequeña en una captura moderna ni recuperar información perdida.

## Desinstalar

Para la instalación predeterminada elimina estas dos rutas desde tu gestor de
archivos: `~/.local/share/restaurador-fotografico` y
`~/.local/share/applications/restaurador-fotografico.desktop`.

## Contenido

- `app/main.py`: interfaz Qt.
- `app/engine.py`: procesamiento y exportación.
- `app/selftest.py`: pruebas funcionales del motor y la interfaz.
- `runtime/`: intérprete y dependencias incluidas.
- `licenses/`: avisos y licencias de terceros.
- `manifest.json`: versión de plataforma y componentes.

No incluye las fotografías personales usadas durante el desarrollo.
