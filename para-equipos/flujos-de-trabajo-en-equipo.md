# Flujos de trabajo en equipo

*English: [team-workflows.md](../for-teams/team-workflows.md)*

Qué corre un vault de equipo que un vault personal no puede. Seis flujos que normalmente pagan la instalación por sí solos.

## 1. Pipeline de reunión a decisión

Las reuniones terminan. Las transcripciones aterrizan en el vault vía Granola, Gemini, Otter, o la herramienta de transcripción que tu equipo ya use. El sistema las recoge y:

1. Etiqueta la reunión por proyecto y participantes.
2. Extrae los action items y rutea cada uno al dueño correcto según el rol, no a mano.
3. Extrae las decisiones y las archiva en un log de decisiones con quién decidió, qué se decidió, qué trade-offs se nombraron, y un campo de resultado en blanco para rastrear después.
4. Redacta mensajes de seguimiento para que el dueño los revise y los envíe.

Qué se rompe en un vault personal: los action items se rutean a "tú". En un equipo tienen que rutearse a María, Diego, o Ana según a quién realmente le pertenecen, y cada dueño necesita ver sus items sin tener que leer cada nota de reunión.

## 2. Ritual semanal del equipo

Cada lunes, un solo comando corre la revisión semanal del equipo:

1. Trae todas las reuniones, decisiones, y action items de la última semana.
2. Saca a flote qué se movió, qué se estancó, y qué se cayó.
3. Lista los loops abiertos de más de 14 días: cosas que alguien prometió hacer y no hizo.
4. Produce un resumen de una página que el equipo lee antes de la reunión semanal.

La reunión semanal se convierte en 30 minutos de decisiones en vez de 60 minutos de actualizaciones de estatus.

## 3. Onboarding con memoria institucional

Una persona nueva entra el día 1. En vez de preguntarle a cada senior "qué decidimos sobre X" durante seis semanas, le pregunta al vault:

- ¿Por qué nos movimos del CRM anterior?
- ¿Cuál es nuestra política sobre descuentos en deals enterprise?
- ¿Quién es dueño de la relación con ese proveedor?
- ¿Qué decidieron los fundadores sobre las prioridades de Q3?

Cada respuesta vuelve con la entrada del log de decisiones, la reunión donde se discutió, y las personas que estaban en la sala. La persona nueva está operando al nivel de conocimiento de la semana 6 el día 1.

Qué se rompe en un vault personal: no hay memoria institucional. Todo vive en la cabeza del fundador. El onboarding toma semanas porque la transferencia de conocimiento es síncrona y se interrumpe.

## 4. Delegación a contratistas con contexto

Cada tarea de contratista en el vault de equipo carga cuatro campos:

- **Qué** es la tarea.
- **Dónde** vive el trabajo (qué docs, qué carpeta, qué ejemplos previos).
- **Forma** que debe tener la entrega (formato, longitud, voz, una muestra funcional).
- **Canal** por el cual entregarla (borrador de email, mensaje de Slack, subida a una carpeta).

Las tareas que no incluyen los cuatro campos quedan bloqueadas al momento de guardar por un hook. El contratista lee la tarea una vez y entrega. Sin preguntas de aclaración, sin salidas fuera de forma, sin horas desperdiciadas.

Qué se rompe sin esto: los contratistas reciben one-liners ("escribe el email de outreach"), pasan dos horas adivinando qué se quería, y entregan algo que el fundador reescribe desde cero. La disciplina alrededor de los cuatro campos es pequeña. Mantenerla sin herramientas es donde fallan la mayoría de los equipos.

## 5. Registro de Hechos Canónicos

Cada doc de alto impacto que el equipo publica (pitch deck, one-pager de ventas, memo para inversionistas, sitio de marketing) contiene claims numéricos: tamaño de mercado, tasas de crecimiento, cantidades de clientes, cifras de ingresos, quotes atribuidas. Un solo número mal citado entre dos archivos es la forma más rápida de perder un inversionista o un deal.

El vault de equipo mantiene un archivo `Hechos Canónicos.md` como fuente única de verdad para cada número, fuente, y atribución que aparece en cualquier material de cara externa. Cada entrada carga:

- El claim ("el tamaño del mercado es $X mil millones")
- La fuente tier-1 (reporte primario, no una cita secundaria ni un resumen de content-mill)
- El año de los datos
- La URL y la fecha de acceso

Cualquier archivo bajo las carpetas de raise, ventas, o marca que cite un número tiene que rastrear hasta Hechos Canónicos. Cuando un número en Hechos Canónicos se actualiza, un chequeo de grep marca cada archivo descendiente que todavía carga la versión vieja. La divergencia entre Hechos Canónicos y cualquier asset externo es un defecto de stop-ship antes de que algo se envíe.

Qué se rompe sin esto: cuatro números distintos de tamaño de mercado terminan en cinco assets de inversionistas distintos, un LP busca uno en Google, encuentra una contradicción, y se va. Tenías una sola tarea: no contradecirte a ti mismo en una hoja de especificaciones.

## 6. Cableado de playbook a tarea (prevención de huérfanos)

Cuando escribes un playbook paso a paso para un contratista o miembro del equipo (un doc de "Instrucciones para [Nombre]"), el playbook es inútil a menos que esté enlazado desde una tarea viva en el sistema de to-dos. Un playbook solo es trabajo invisible: el contratista nunca lo ve, el líder del equipo se olvida de que existe, el trabajo nunca se entrega.

Cada archivo de playbook tiene que estar emparejado con una tarea en el archivo de to-dos del equipo que:

- Enlace al playbook con un wikilink
- Cargue dueño, área, prioridad, y fecha de entrega
- Esté espejada en la vista personal del dueño

El cierre de sesión corre un scan de playbooks huérfanos: cualquier archivo "Instrucciones para [Nombre]" modificado en esta sesión se chequea contra el archivo de to-dos del equipo. Si no existe una tarea que coincida, la sesión no puede cerrarse hasta que se agregue una tarea o el playbook se marque `status: reference-only` en su frontmatter.

Qué se rompe sin esto: pasas 45 minutos escribiendo un playbook cuidadoso, te olvidas de cablearlo a una tarea, y el contratista nunca lo ve. El trabajo que tenía que entregarse antes del viernes no se entrega porque nadie supo que estaba sobre la mesa.

---

Si estos flujos coinciden con lo que tu equipo ya está intentando hacer y fallando, [trabajar-conmigo.md](trabajar-conmigo.md) tiene los paquetes para instalarlos.
