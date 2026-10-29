# Proyecto: BrilloMusical (Windows)

App de escritorio para Windows que:
1. Pone un brillo alrededor de la pantalla con el color de la portada de la canción que suena en YouTube Music (YouTube Premium).
2. Muestra la letra sincronizada con efecto de constelación (palabras como estrellas unidas por líneas).

Resultado final: una App ejecutable (.exe).

## Instrucciones básicas (obligatorias)
1. **No hablar cosas que no sean necesarias.** Respuestas cortas y al grano.
2. **Hacer preguntas cuando el usuario pida cambios.** Antes de aplicar un cambio, confirmar lo que no esté claro.
3. **Todo pasa por todos los agentes.** Cada tarea la revisan todos los agentes, discuten ideas entre ellos y el Capitán decide. Ver el flujo abajo.
4. **Builds:** nunca ejecutar el build por el usuario. Dejar un archivo listo para que él lo ejecute (por ejemplo `build.bat`) que genere el `.exe`.

## Agentes
| Agente | Archivo | Rol |
|---|---|---|
| Capitán | `.claude/agents/capitan.md` | Coordina, abre la discusión, decide y responde al usuario |
| Diseño | `.claude/agents/diseno.md` | Aspecto visual: brillo, constelación, colores, animaciones |
| Lógica | `.claude/agents/logica.md` | Arquitectura, flujo de datos, sincronización, casos límite |
| Programación | `.claude/agents/programacion.md` | Escribe el código |
| Pruebas | `.claude/agents/pruebas.md` | Revisa errores, rendimiento y que todo funcione en Windows |
| Empaquetado | `.claude/agents/empaquetado.md` | Prepara el archivo de build y el `.exe` |
| Marketing | `.claude/agents/marketing.md` | Textos, experiencia del usuario nuevo, presentación y errores de cara al usuario |
| Diseño avanzado | `.claude/agents/diseno-avanzado.md` | Lleva el aspecto visual a nivel profesional (composición, color, tipografía, coherencia) |
| Animaciones | `.claude/agents/animaciones.md` | Transiciones, curvas, partículas y efectos; investiga referencias |

## Flujo de trabajo (para cada tarea o cambio)
1. **Capitán** recibe la petición. Si algo no está claro, pregunta al usuario y espera.
2. **Ronda de ideas:** cada agente da su propuesta y sus riesgos desde su área.
3. **Discusión:** los agentes comentan las propuestas de los demás (acuerdos, objeciones, alternativas).
4. **Decisión:** el Capitán elige el plan final y lo resume en pocas líneas.
5. **Ejecución:** Programación implementa; Diseño y Lógica revisan; Pruebas valida; Empaquetado actualiza el build si hace falta.
6. **Entrega:** el Capitán informa al usuario de forma breve qué se hizo y qué debe ejecutar.

Registrar cada decisión en `docs/decisiones.md` (fecha, petición, plan elegido, motivo).
