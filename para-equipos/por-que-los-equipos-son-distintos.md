# Por qué los equipos son distintos

*English: [why-teams-are-different.md](../for-teams/why-teams-are-different.md)*

La versión personal de ai-brain-starter funciona de maravilla para una persona. La instalas. Tu archivo de contexto te conoce. Tu vault crece contigo. Tu IA recuerda lo que decidiste el martes pasado.

Correr el mismo sistema en un equipo introduce problemas que la versión personal nunca tuvo que resolver. Acá están los cuatro grandes, en el orden en que suelen romper las cosas.

## 1. Edición concurrente

Obsidian fue construido para un usuario por vault. Cuando dos personas editan la misma nota al mismo tiempo, el último guardado gana y el trabajo de la otra persona desaparece. Puedes superponer Git, Google Drive, o iCloud por encima, pero cada uno tiene sus trade-offs: conflictos de merge, lag de sincronización, huecos de permisos, o wikilinks rotos.

Un vault de equipo real necesita una estrategia de edición concurrente. Esa estrategia depende del tamaño del equipo, las herramientas, los hábitos offline, y qué personas tienen permiso de tocar qué carpetas. No hay una sola respuesta correcta, pero la incorrecta pierde trabajo.

## 2. Permisos y límites

No toda persona en el equipo debería ver toda nota. Las notas de HR, legal, financieras y de estrategia a nivel de fundadores necesitan alcance acotado. El vault personal no tiene concepto de permisos. Corre un vault compartido sin límites y tarde o temprano alguien lee algo que no debería haber leído, y tienes un problema.

Existen opciones: varios vaults enlazados, permisos a nivel de carpeta en Google Drive o Dropbox, subconjuntos de solo lectura, symlinks que incluyen o excluyen selectivamente. Cada opción tiene trade-offs. Necesitas decidir el modelo antes de que el equipo esté en el vault, no después.

## 3. Ruteo de reunión a decisión

En un vault personal, tiras la transcripción de una reunión en una nota y sigues. Claude puede procesarla después. En un vault de equipo, cada reunión tiene múltiples dueños, múltiples action items ruteados a personas distintas, y múltiples decisiones que tienen que aterrizar en el archivo correcto, no en el inbox equivocado o en un hilo de Slack olvidado.

El pipeline de reunión a decisión tiene que rutear por rol, no por persona. Esa lógica de ruteo no está en la versión personal. Tiene que ser diseñada.

## 4. Memoria institucional que sobrevive la rotación

En un vault personal, todo vive en tu cabeza más tu vault. Si te vas de tu propia empresa, el vault se va contigo. En un vault de equipo, el punto es que el vault sobreviva a la rotación individual. Cuando tu líder de operaciones renuncia, la memoria institucional se queda. Cuando entra alguien nuevo, le puede preguntar a Claude "qué decidimos sobre X hace seis meses" y obtener una respuesta con contexto adjunto.

Hacer que eso sea verdad requiere una arquitectura de información distinta: roles como objeto de primera clase, decisiones logueadas con racional y trade-offs, artefactos de reunión enlazados a decisiones, decisiones enlazadas a resultados. Esto es una decisión de diseño, no solo una instalación.

## Qué significa esto en la práctica

Puedes construir un vault de equipo tú mismo usando la versión personal como punto de partida. El camino existe. El costo es tiempo: los cuatro problemas anteriores tienen cada uno varias soluciones con trade-offs, y la mayoría de equipos aprenden cuáles trade-offs importan solo después de que el primero se rompe.

La versión de equipo no es magia distinta. Es el mismo sistema con estas cuatro decisiones pre-tomadas basándose en cómo funciona tu equipo específico.

Si eso suena al trade correcto, [flujos-de-trabajo-en-equipo.md](flujos-de-trabajo-en-equipo.md) cubre qué corre la versión instalada. Si quieres que te la construya, [trabajar-conmigo.md](trabajar-conmigo.md) es el menú.
