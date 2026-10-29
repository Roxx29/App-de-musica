# BrilloMusical

**Tu música, en la luz de tu pantalla.**

BrilloMusical pinta los bordes de tu pantalla con los colores de la portada de lo que suena en YouTube Music y muestra la letra sincronizada de tres formas. En **Constelación**, cada palabra es una estrella que se une a la anterior mientras se canta. En **Latido**, la letra aparece grande y se mueve al ritmo de la canción. En **Cinta**, la palabra que suena recorre una cinta que se retuerce en 3D, sobre papel claro.

## Empieza en 30 segundos

1. Descomprime la carpeta `BrilloMusical`. No separes el `.exe` de su carpeta `_internal`.
2. Abre `BrilloMusical.exe`. Aparecerá una estrella en la bandeja del sistema. Si no la ves, pulsa la flecha **^** que hay junto al reloj.
3. Pon una canción en YouTube Music y haz doble clic en la estrella para abrir la letra.

## Qué hace

- **Brillo en los bordes**: un halo con los colores de la portada que sigue el ritmo. Puedes elegir entre Estático, Respirar, Al ritmo, Giratorio, Aurora, Destello, Fuego, Ondas y Arcoíris. También puedes dejarlo en **Automático** para que cambie según el ambiente de la canción.
- **Tres estilos de letra**:
  - **Constelación**: cada estrofa forma una constelación nueva y pasa a la siguiente con una transición (Viaje, Remolino, Explosión, Lluvia de estrellas, Polvo, Reconstelar u Onda). La transición puede ser fija, Aleatoria o Automática.
  - **Cinta**: fondo blanco hueso y letra negra condensada que avanza por una cinta en S. La cinta se retuerce en perspectiva y al final se ve su reverso en espejo; la palabra que suena toma el color de la portada. Al empezar cada canción aparece un rótulo con el título escrito letra a letra bajo una franja de flechas. Si no hay letra, la cinta repite el título.
  - **Latido**: la línea que suena se ve grande y en el centro, con efectos de tipografía cinética que dependen del ambiente. En las canciones tranquilas la letra sube suave o se rellena tipo karaoke. En las normales, las palabras golpean o se mecen. En las intensas, la letra cae en cascada o entra con impacto, en mayúsculas.
- **Portada de fondo**: difuminada, en movimiento, con efecto Ken Burns o al ritmo. La portada HD sale de iTunes y Deezer.
- **Carátula**: una tarjeta con título, artista y progreso. Si la canción no tiene letra, o llega un instrumental largo, la carátula se mueve al centro en grande.
- **Pantalla completa** para dejar la letra puesta en una tele o en un segundo monitor.
- Se oculta sola durante los juegos a pantalla completa.

## Controla todo

**Menú de rueda**: acerca el ratón a la parte de arriba, en el centro de la ventana de la letra. Aparecerá un botón. Haz clic en él, o deja el ratón encima un momento, y se abrirá la rueda con Estilo, Transición, Fondo, Carátula, Calidad y Pantalla completa. Cada clic en un sector pasa a la siguiente opción.

**Bandeja**: haz clic derecho en la estrella para ver todas las opciones, también las del efecto del borde y la sincronización de la letra.

**Atajos** (en la ventana de la letra):

| Tecla | Acción |
|---|---|
| **M** | Abrir o cerrar el menú de rueda |
| **F** / **F11** / doble clic | Pantalla completa |
| **Esc** | Cerrar la rueda o salir de pantalla completa |
| **L** | Cambiar el estilo de letra (Constelación / Latido / Cinta) |
| **B** | Cambiar el fondo |
| **C** | Cambiar la posición de la carátula |
| **T** | Cambiar la transición |
| **← / →** | Retrasar o adelantar la letra 0,1 s (se recuerda en cada canción) |
| **H** | Ver los atajos |

## Equipos modestos

En *Calidad*, el modo **Automática** mide lo que le cuesta a tu equipo mover la animación. Si va justo, pasa a **Ligera**: 30 fotogramas por segundo, sin estrellas que titilan ni nebulosa, y sin chispas. Cuando lo hace, te avisa una vez. En los equipos de 2 núcleos o menos empieza ya en Ligera. Si prefieres decidirlo tú, elige **Alta** o **Ligera** en la rueda o en la bandeja.

## Requisitos

- Windows 10 u 11.
- YouTube Music en un navegador basado en Chromium (Chrome, Edge, Opera, Brave…).

## Privacidad

BrilloMusical lee la canción que suena desde los controles multimedia de Windows. Para buscar la letra y la portada HD envía **solo el título y el artista** a LRCLIB, iTunes y Deezer. Puedes desactivar la portada HD en *Carátula → Portada HD*. La app no guarda ni envía nada más. La caché está en `%LOCALAPPDATA%\BrilloMusical`.

## Problemas comunes

- **No detecta la canción**: comprueba que suena en YouTube Music desde el navegador y que Windows muestra sus controles multimedia (al subir o bajar el volumen con las teclas debería aparecer la canción).
- **La animación va a tirones**: elige *Calidad → Ligera* en la rueda o en la bandeja.
- **La letra va adelantada o atrasada**: usa ← / → en la ventana de la letra, o *Sincronizar letra* en la bandeja.
- **No encuentro cómo salir de pantalla completa**: pulsa **Esc** o haz doble clic.
- **El .exe no arranca**: abre el que está en `dist\BrilloMusical\`, no el de `build\`.

## Para desarrolladores

Con Python 3.12 instalado, haz doble clic en `build.bat`. El script instala las dependencias, pasa los tests y deja el programa en `dist\BrilloMusical\BrilloMusical.exe`. Si abres la app con la variable `BRILLOMUSICAL_DEBUG=1`, guarda un registro detallado en `app.log`.

## Créditos

Letras: [LRCLIB](https://lrclib.net). Portadas: iTunes Search API y Deezer API. Iconos: Segoe MDL2 Assets de Windows. Hecho con Python y PySide6.
