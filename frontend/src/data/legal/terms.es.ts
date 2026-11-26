import type { LegalContent } from "./types";
import { COMPANY, COMPANY_ADDRESS, CONTACT_EMAIL, GOVERNING_LAW_ES, MIN_AGE, SITE } from "../legal";

export function esTerms(): LegalContent {
	const glance = [
		`videomk lo ofrece ${COMPANY}. Debes tener al menos ${MIN_AGE} años y contar con el permiso de tus padres si eres menor de 18.`,
		"Los videos los crea la IA a partir de lo que pides. Eres responsable de lo que pides, de las fotos que adjuntas y de revisar y etiquetar el resultado antes de publicarlo.",
		"Eres dueño de tus descripciones y fotos y, entre tú y nosotros, de tus videos. Solo usamos tu contenido para prestar el servicio, como explica la Política de privacidad.",
		"Los créditos pagan los videos: 1 crédito por minuto iniciado (el doble en 4K). Si un video falla o se detiene, se reembolsa. Los créditos no tienen valor en efectivo.",
		"Algunas imágenes y clips proceden de la biblioteca de contenido generado con IA de videomk, que puedes usar dentro de tus videos. Las imágenes y clips de archivo proceden de otros proveedores bajo sus propias licencias: si publicas el video, conserva los créditos que indicamos en su descripción.",
		"Nada de videos dañinos, engañosos o ilegales, ni nada que ponga palabras en boca de una persona real. La sección 8 enumera lo que detenemos.",
	];
	const sections = [
		{ title: "Aceptación", paras: [
			`Estos Términos son el acuerdo entre tú y ${COMPANY} (“videomk”, “nosotros”)${COMPANY_ADDRESS ? `, ${COMPANY_ADDRESS}` : ""}, para las apps de videomk para iPhone y Android y el sitio web ${SITE}. Al crear una cuenta o usar videomk los aceptas, así como nuestra Política de privacidad. Si no los aceptas, no uses videomk.`] },
		{ title: "Quién puede usar videomk", paras: [
			`Debes tener al menos ${MIN_AGE} años, o la edad superior a partir de la cual puedes usar un servicio en línea sin el consentimiento de tus padres donde vives. Si eres menor de 18 años, necesitas el permiso de uno de tus padres o de tu tutor, que será responsable de tu uso. Si usas videomk para una organización, confirmas que puedes obligarla.`,
			"Danos información veraz. Ten una sola cuenta por persona y mantén en secreto tus datos de inicio de sesión: eres responsable de lo que ocurra con tu cuenta. Avísanos de inmediato si crees que otra persona la ha usado."] },
		{ title: "Cuentas e inicio de sesión", paras: [
			"Puedes registrarte con un correo y una contraseña, o con Google o Apple donde lo ofrezcamos. Si usas Google o Apple, sus términos también se aplican a ese inicio de sesión. Podemos vincular un inicio de sesión de Google o Apple a una cuenta existente que tenga el mismo correo verificado. Puedes eliminar tu cuenta en cualquier momento en la app (Ajustes, Eliminar cuenta) o por correo, como se describe en /es/delete-account."] },
		{ title: "Qué hace videomk", paras: [
			"Describes un video escribiendo o hablando y, si quieres, adjuntas fotos o las eliges de tu biblioteca privada Mi biblioteca. videomk revisa la petición, investiga datos cuando hace falta, escribe un guion, busca imágenes y clips, añade una voz de narrador sintética, música de fondo y subtítulos, y crea un video que puedes ver, editar y compartir.",
			"videomk es un servicio nuevo. Las funciones, los idiomas, las duraciones, los límites y los precios pueden cambiar, y algunas cosas pueden no funcionar como esperas."] },
		{ title: "Créditos", bullets: [
			"Los videos se pagan con créditos. 1 crédito cubre un minuto iniciado de video (un video de 61 segundos cuesta 2 créditos), hasta 12 minutos. Un video en 4K cuesta el doble. La app muestra el costo antes de crear un video, y la duración que eliges es la que creamos y cobramos. Editar un video que ya hiciste es gratis.",
			"Créditos gratuitos: las cuentas nuevas reciben créditos de bienvenida que caducan a los 30 días, y puedes reclamar un pequeño crédito gratuito diario que caduca esa misma noche. Los créditos gratuitos pueden cambiarse, reducirse o suspenderse, y podemos negarlos cuando veamos abusos, como muchas cuentas creadas para acumular créditos.",
			"Si un video falla o lo detiene nuestro control de seguridad, se devuelven los créditos que usó. Si los créditos que gastaste ya habían caducado, te los devolvemos como créditos que duran 24 horas.",
			"Los créditos no tienen valor en efectivo, no se pueden vender ni transferir, y se pierden si tu cuenta se elimina o se cierra por incumplir estos Términos.",
			"Todavía no es posible comprar créditos. Cuando lo sea, las compras se harán a través de Apple o Google según sus términos, y el plan o paquete de créditos tendrá sus propios términos sobre precio, renovación, cancelación y reembolsos. Esos términos no te quitarán los derechos que te da la ley, incluido cualquier derecho a un reembolso o a cancelar dentro de un plazo determinado."] },
		{ title: "Tu contenido y la licencia que nos das", paras: [
			"“Tu contenido” son tus descripciones, respuestas, fotos, tu biblioteca Mi biblioteca y cualquier otra cosa que nos des. Conservas todos los derechos que tengas sobre él.",
			"Nos concedes una licencia mundial y no exclusiva para almacenar, copiar, procesar y mostrar tu contenido, y para enviarlo a los proveedores de servicios que nombra la Política de privacidad, solo en la medida necesaria para que videomk funcione para ti: crear, guardar, mostrar, editar y eliminar tus videos y fotos, mantener el servicio seguro y cumplir nuestras obligaciones legales. Termina cuando se elimina tu contenido, salvo las copias limitadas que la Política de privacidad indica que permanecen durante un tiempo breve. No usamos tu contenido para entrenar modelos de IA.",
			"Confirmas que tienes derecho a darnos tu contenido y que no infringe la ley, los derechos de otra persona ni estos Términos."] },
		{ title: "Fotos, voces e imagen de personas", paras: [
			"Adjunta solo fotos que tengas derecho a usar. Si una foto muestra a otras personas, asegúrate de que están de acuerdo en aparecer en un video, y ten especial cuidado con las fotos de menores: úsalas solo si eres su padre, madre o tutor, o tienes el permiso de sus padres.",
			"No uses videomk para crear un video que muestre o imite a una persona real haciendo o diciendo algo que no hizo ni dijo, ni que use la imagen o la voz de alguien para engañar. Las voces de los narradores de videomk son voces sintéticas, no grabaciones de personas reales, y videomk no copia la voz de nadie."] },
		{ title: "Lo que no puedes hacer", paras: [
			"Nuestro control de seguridad detiene las peticiones que entran en estos grupos. Las peticiones educativas, informativas, históricas, de ficción y de información médica que tratan un tema están permitidas. Una petición se detiene cuando su propósito o su contenido es el daño. No puedes usar videomk para crear:"], bullets: [
			"nada que sexualice a menores, en ninguna forma;",
			"instrucciones prácticas o ayuda para herir o matar a personas, o para planear o llevar a cabo un ataque o actos de terrorismo;",
			"material dirigido a una persona privada para acosarla, perseguirla, intimidarla o divulgar sus datos personales, incluido averiguar o publicar dónde vive, dónde trabaja o cómo contactarla;",
			"contenido sexual explícito o pornografía, o contenido íntimo o sexual sobre una persona real sin su consentimiento;",
			"violencia explícita, tortura o crueldad como finalidad del video;",
			"métodos, incitación o guías paso a paso para el suicidio o las autolesiones;",
			"cómo fabricar armas, explosivos o drogas ilegales, o cómo eludir las leyes sobre ellos;",
			"contenido de odio, deshumanizante o de acoso contra personas por su raza, religión, sexo, orientación, discapacidad o nacionalidad;",
			"fraudes, estafas, suplantación de identidad (phishing), documentos falsificados, suplantaciones o engaños al estilo deepfake que ponen palabras en boca de una persona real;",
			"malware, o ayuda para entrar sin permiso en los sistemas o cuentas de otras personas;",
			"propaganda, reclutamiento o elogio de grupos terroristas o extremistas violentos;",
			"desinformación electoral o sobre la salud presentada como un hecho;",
			"cualquier otra cosa claramente destinada a causar un daño grave a las personas."], after: [
			"Tampoco puedes atacar, sobrecargar, extraer datos de forma masiva, sondear ni aplicar ingeniería inversa a videomk, eludir sus límites (por ejemplo, con muchas cuentas para conseguir créditos gratuitos), revenderlo, ni usarlo para crear un producto competidor o para entrenar modelos de IA.",
			"El control es automático y puede cometer errores. Si crees que hemos detenido algo por error, escríbenos."] },
		{ title: "Qué ocurre si incumples las normas", paras: [
			"Una petición que incumple las normas se detiene y no se cobra ningún crédito. Registramos la detención como describe la Política de privacidad. Tres detenciones en 24 horas pausan la creación de videos en tu cuenta durante 24 horas. Una petición de los grupos más graves (menores, instrucciones para herir a personas, dirigirse a una persona privada), o las detenciones repetidas durante un mes, ponen tu cuenta en espera mientras la revisamos. También podemos eliminar contenido, suspender o cerrar cuentas y denunciar a las autoridades el contenido ilegal.",
			`Puedes pedirnos que revisemos una pausa, una espera o un cierre escribiendo a ${CONTACT_EMAIL}. Lo estudiaremos, te diremos lo que decidimos y lo levantaremos si fue un error.`] },
		{ title: "Videos generados con IA", paras: [
			"Los videos los produce la IA y pueden ser incorrectos, incompletos, estar desactualizados, tener sesgos o no ser adecuados para tu propósito, y las imágenes, los clips y los subtítulos pueden no coincidir perfectamente. No prometemos que un video sea exacto ni original, ni que no se parezca a la obra de otra persona. Un video no es asesoramiento jurídico, médico, financiero ni profesional de ningún otro tipo.",
			"Eres responsable de revisar un video, y de lo que hagas con él, antes de publicarlo o de confiar en él. Muchas plataformas y algunas leyes exigen indicar cuándo un contenido se ha creado o modificado con IA: sigue las normas del lugar donde publicas y etiqueta el video donde lo pidan, por ejemplo con las etiquetas de contenido de IA de YouTube, TikTok e Instagram. Cuando una plataforma o la app lo pide, etiquetamos como tal el contenido multimedia generado con IA; eso nunca sustituye tu propia obligación de informar."] },
		{ title: "De quién es el video", paras: [
			"Entre tú y nosotros, eres dueño de los videos que creas y puedes usarlos con fines personales y comerciales, sujeto a estos Términos y a las licencias del material de terceros que contienen (sección siguiente). En la medida en que tengamos algún derecho sobre un video, te lo cedemos. El resultado de la IA no siempre está protegido por derechos de autor, y pueden crearse videos parecidos para otras personas. Conservamos nuestros derechos sobre la app, el software, los diseños, la marca y la tecnología."] },
		{ title: "Imágenes, clips, música y voces en tus videos", paras: [
			"Biblioteca multimedia de IA propia de videomk: algunas imágenes y clips breves de tu video proceden de una biblioteca de contenido generado con IA que videomk creó con modelos comerciales de IA generativa y revisó. Somos dueños, o tenemos el control, de todos los derechos que tenemos sobre ella. El material generado puramente con IA puede tener una protección de derechos de autor limitada o nula en algunos países, así que no podemos prometer que nadie más pueda usar algo parecido.",
			"Puedes usar estas imágenes y clips de la biblioteca dentro de los videos que crees con videomk, también con fines comerciales, sin necesidad de dar crédito. No puedes revenderlos, compartirlos ni redistribuirlos como archivos multimedia independientes, extraer ni copiar la biblioteca, usarlos para crear una biblioteca o un servicio competidor, ni usarlos para entrenar modelos de IA.",
			"La biblioteca no se crea a partir del contenido de nadie. Se genera a partir de instrucciones genéricas que escribimos nosotros, y tus descripciones, fotos y archivos subidos nunca se usan para crearla ni mejorarla. La biblioteca está pensada para mostrar escenas genéricas y no personas reales, y cualquier parecido con una persona real es involuntario.",
			"Imágenes y clips de archivo: otras imágenes y clips proceden de bibliotecas como Pexels, Pixabay, Unsplash, Openverse, NASA y Wikimedia Commons. Cada uno se usa bajo su propia licencia, y algunas exigen dar crédito. Mostramos los créditos en el video y los incluimos en su descripción. Si publicas el video, conserva esa lista con él. No saques las imágenes ni los clips de archivo del video para venderlos, compartirlos o usarlos por separado, y no los uses de formas que sus licencias prohíben, como dar a entender que su autor o proveedor te respalda.",
			"La música de fondo la genera videomk. La narración usa voces sintéticas de Amazon Polly. No las presentes como grabaciones de personas reales."] },
		{ title: "Compartir", paras: [
			"Tus videos son privados hasta que los compartes. Cuando compartes un video, las personas que lo reciben, o reciben un enlace a él, pueden verlo y copiarlo. Eres responsable de lo que compartes y de con quién lo compartes."] },
		{ title: "Servicios de terceros y tiendas de aplicaciones", paras: [
			"videomk depende de otros servicios, como AWS, proveedores de modelos de IA, buscadores y bibliotecas de contenido, Apple y Google. No somos responsables de sus servicios, que pueden cambiar o dejar de funcionar. La Política de privacidad los nombra.",
			"Si obtienes la app en la App Store de Apple o en Google Play, estos Términos son entre tú y nosotros, no con Apple ni con Google. Ellos no tienen ninguna obligación de dar soporte a la app. Apple y sus filiales son terceros beneficiarios de estos Términos respecto a la app de iPhone y pueden hacerlos valer contra ti. También se aplican los términos de la tienda."] },
		{ title: "Derechos de autor y otras reclamaciones", paras: [
			`Si crees que un video creado con videomk infringe tus derechos de autor u otros derechos, o es dañino o ilegal, escribe a ${CONTACT_EMAIL} con el asunto “Notice”. Indica, por favor: tu nombre y datos de contacto; el título o el enlace del video; cuál es la obra y por qué dices que es tuya (o qué es ilegal); el material exacto que reclamas; una declaración de que crees de buena fe que el titular, su representante o la ley no permiten ese uso; y una declaración de que tu aviso es exacto y, en un aviso de derechos de autor, de que eres el titular o estás autorizado para actuar en su nombre.`,
			"Revisamos los avisos con prontitud, podemos retirar material e informar al titular de la cuenta, que puede responder con una contranotificación. Podemos cerrar las cuentas de quienes infrinjan de forma reiterada. Los avisos falsos presentados a sabiendas pueden tener consecuencias legales para quien los envía."] },
		{ title: "Disponibilidad, suspensión y cierre", paras: [
			"Procuramos que videomk sea fiable, pero no prometemos que esté siempre disponible ni libre de errores. Podemos cambiar, suspender o detener todo el servicio o una parte, y avisaremos cuando razonablemente podamos si el cambio te perjudica.",
			"Puedes dejar de usar videomk y eliminar tu cuenta en cualquier momento. Podemos suspender o cerrar tu cuenta si incumples estos Términos, si la ley lo exige o si pones en riesgo a otras personas o al servicio; normalmente te explicaremos el motivo y cómo pedir una revisión. Cuando una cuenta se cierra, tu contenido se elimina como describe la Política de privacidad, así que descarga o comparte antes lo que quieras conservar."] },
		{ title: "Exclusiones y límites de nuestra responsabilidad", paras: [
			"En la medida en que la ley lo permita, videomk se ofrece “tal cual” y “según disponibilidad”, y no prometemos que cumpla tus necesidades ni que sus resultados sean exactos.",
			"Nada en estos Términos limita ningún derecho que tengas como consumidor, ni la responsabilidad que no pueda limitarse legalmente, incluida la derivada de fraude o de muerte o lesiones personales causadas por negligencia.",
			`Sin perjuicio de lo anterior, ${COMPANY} no es responsable de las pérdidas indirectas o consecuentes, ni de la pérdida de beneficios, de negocio, de datos o de reputación comercial, y nuestra responsabilidad total por cualquier reclamación se limita a la mayor de estas cantidades: lo que nos pagaste en los 12 meses anteriores a la reclamación y £100.`] },
		{ title: "Tu responsabilidad ante nosotros", paras: [
			"En la medida en que la ley lo permita, cubrirás las pérdidas y los costos razonables que suframos por reclamaciones de terceros derivadas de tu contenido, de tu incumplimiento de estos Términos o de tu uso ilegal de videomk. Esto no se aplica a los consumidores más allá de lo que permita la ley, ni a las pérdidas que hayamos causado nosotros."] },
		{ title: "Cambios en estos Términos", paras: [
			"Podemos actualizar estos Términos, por ejemplo cuando añadamos planes de pago o nuevas funciones. Cambiaremos la fecha de arriba y, si los cambios son importantes, te avisaremos en la app o por correo al menos 14 días antes de que entren en vigor, salvo que el cambio sea necesario antes por motivos legales o de seguridad. Si no aceptas un cambio, puedes dejar de usar videomk y eliminar tu cuenta. Si sigues usándolo después de que el cambio entre en vigor, lo aceptas."] },
		{ title: "Ley aplicable y controversias", paras: [
			`Estos Términos se rigen por las leyes de ${GOVERNING_LAW_ES}, y los tribunales de ${GOVERNING_LAW_ES} tienen jurisdicción exclusiva, salvo que, si eres consumidor, conservas la protección de las leyes imperativas del país donde vives y cualquier derecho a presentar una reclamación ante los tribunales de allí. Por favor, escríbenos primero a ${CONTACT_EMAIL} para que intentemos resolverlo. Si alguna parte de estos Términos no puede hacerse cumplir, el resto sigue en vigor.`] },
		{ title: "Contacto", paras: [`Preguntas sobre estos Términos: ${CONTACT_EMAIL}.`] },
	];
	return { title: "Términos y condiciones", intro: "Las reglas para usar videomk, incluidos los créditos, los videos creados con IA y tus responsabilidades.", glance, sections };
}
