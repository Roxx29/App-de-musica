# BrilloMusical

**Tu música, en la luz de tu pantalla.**

BrilloMusical ilumina los bordes de tu pantalla con los colores de la portada de lo que suena en YouTube Music y muestra la letra sincronizada como una constelación: cada palabra es una estrella que se une a la siguiente mientras se canta.

## Qué hace

- **Brillo en los bordes**: un halo con los colores de la portada que reacciona al ritmo. Efectos: Estático, Respirar, Al ritmo, Giratorio, Aurora, Destello, Fuego, Ondas y Arcoíris, o **Automático**, que cambia según el ambiente de la canción (tranquila, normal, intensa, subidas fuertes).
- **Letra en constelación**: letras sincronizadas de LRCLIB. Cada estrofa es una constelación nueva con su transición: Viaje, Remolino, Explosión, Lluvia de estrellas, Polvo, Reconstelar u Onda. También puede ser **Automática** (según la música) o **Aleatoria**.
- **Portada de fondo**: difuminada, en movimiento, Ken Burns, al ritmo o **Automático**, con portadas HD de iTunes y Deezer.
- **Carátula**: tarjeta en la esquina con título, artista y progreso, arriba a la izquierda, como marca de agua u oculta. Si la canción no tiene letra, o hay un instrumental largo, la carátula viaja al centro en grande.
- Se oculta sola durante juegos a pantalla completa y consume poca CPU.

## Requisitos

- Windows 10 u 11.
- YouTube Music en un navegador basado en Chromium (Chrome, Edge, Opera, Brave…).

## Instalación

1. Descomprime la carpeta `BrilloMusical`. Mantén la carpeta entera: el `.exe` necesita su carpeta `_internal`.
2. Abre `BrilloMusical.exe`. Aparece una estrella en la bandeja del sistema. Si no la ves, pulsa la flecha **^** junto al reloj.

## Uso

En la estrella de la bandeja, el doble clic abre la letra y el clic derecho abre el menú, con efecto del borde, transición entre estrofas, fondo de la letra, carátula, sincronizar letra y atajos.

Atajos en la ventana de la letra:

| Tecla | Acción |
|---|---|
| **B** | Cambiar fondo |
| **C** | Cambiar posición de la carátula |
| **T** | Cambiar transición |
| **← / →** | Retrasar / adelantar la letra 0,1 s (se recuerda por canción) |
| **H** | Ver los atajos |

## Privacidad

BrilloMusical lee la canción desde los controles multimedia de Windows. Para buscar la letra y la portada HD envía **solo el título y el artista** a LRCLIB, iTunes y Deezer. La portada HD se puede desactivar en *Carátula → Portada HD*. No guarda ni envía nada más. La caché vive en `%LOCALAPPDATA%\BrilloMusical`.

## Problemas comunes

- **No detecta la canción**: comprueba que suena en YouTube Music en el navegador y que Windows muestra sus controles multimedia (las teclas de volumen enseñan la canción).
- **La letra va adelantada o atrasada**: usa ← / → en la ventana de la letra o *Sincronizar letra* en la bandeja. Para investigarlo, abre la app con la variable `BRILLOMUSICAL_DEBUG=1` y revisa `app.log`.
- **El .exe no arranca**: abre el de `dist\BrilloMusical\`, no el de `build\`.

## Generar el ejecutable

Con Python 3.12 instalado, haz doble clic en `build.bat`. Instala las dependencias, pasa los tests y deja el programa en `dist\BrilloMusical\BrilloMusical.exe`.

## Capturas sugeridas

Borde en Fuego y en Aurora; constelación a mitad de estrofa; carátula grande sin letra; las cuatro posiciones de la carátula; un GIF de cada transición.

## Créditos

Letras: [LRCLIB](https://lrclib.net). Portadas: iTunes Search API y Deezer API. Hecho con Python y PySide6.
