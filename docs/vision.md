# MoodTrack — Especificação do Produto

## Visão Geral

O MoodTrack é uma plataforma digital, disponível em versões web e mobile, voltada para o acompanhamento contínuo da saúde mental. O produto conecta dois perfis de usuários — psicólogos e pacientes — em um ambiente onde o cuidado terapêutico se estende para além do horário da sessão, permitindo que o profissional acompanhe a evolução do paciente entre uma consulta e outra com base em dados ricos, organizados e analisados de forma inteligente.

A proposta central é resolver um problema clássico da prática clínica: o psicólogo, na maioria das vezes, só sabe sobre o paciente o que ele relata na sessão semanal. Tudo que aconteceu nos seis dias anteriores depende exclusivamente da memória, da disposição e da capacidade de articulação do paciente naquele momento. O MoodTrack preenche esse intervalo, oferecendo ao paciente um espaço estruturado para registrar seu cotidiano emocional, e ao psicólogo uma visão organizada e analisada desse material, transformando o acompanhamento terapêutico em um processo verdadeiramente contínuo.

A plataforma também atende usuários que desejam fazer apenas o uso pessoal, sem vínculo com um profissional, oferecendo um modo de diário com análise automatizada dos próprios dados como ferramenta de autoconhecimento.

## Para Quem é o MoodTrack

A plataforma é desenhada para três tipos de usuários:

- **Psicólogos em prática clínica** que desejam ampliar a qualidade do acompanhamento dos seus pacientes, organizar melhor seus prontuários e ter ferramentas modernas de apoio à decisão clínica.
- **Pacientes em terapia** que querem participar mais ativamente do próprio processo terapêutico, registrando suas experiências entre sessões e compartilhando-as de forma organizada com seu psicólogo.
- **Pessoas em uso individual** que buscam uma ferramenta de autoconhecimento e registro emocional, sem necessariamente estarem em terapia, e que se beneficiam de análises automatizadas sobre seus próprios padrões.

## Como Funciona — Visão do Paciente

O paciente acessa o MoodTrack com um perfil pessoal próprio. Se está em terapia, ele recebe do seu psicólogo um código único de convite que estabelece o vínculo entre os dois dentro da plataforma. Esse vínculo não é automático nem aberto: o paciente entra com o código, e o psicólogo confirma a conexão do seu lado, garantindo que cada relação terapêutica na plataforma seja autorizada pelas duas partes. Caso o paciente não tenha psicólogo, ele pode usar a plataforma de forma autônoma, no modo diário pessoal.

No dia a dia, o paciente registra seu humor de forma rápida e sem fricção, escolhendo entre representações emocionais e adicionando, se quiser, uma descrição mais detalhada. Pode também escrever pensamentos, relatar situações vividas, descrever sonhos ou registrar reflexões. Os registros podem ser feitos em texto ou em áudio — a plataforma transcreve automaticamente as gravações para que o conteúdo fique disponível em ambos os formatos.

Periodicamente, o paciente também responde a escalas clínicas validadas, como instrumentos reconhecidos para acompanhamento de sintomas de depressão e ansiedade. Essas escalas são curtas, podem ser configuradas pelo psicólogo de acordo com a necessidade do tratamento, e geram gráficos de evolução ao longo do tempo, permitindo visualizar tendências de forma objetiva.

Um aspecto fundamental do MoodTrack é o controle granular de privacidade pelo paciente. Cada registro feito por ele tem uma marcação clara de visibilidade: o paciente decide, por entrada, se aquele conteúdo será compartilhado com o psicólogo ou permanecerá privado. Essa decisão é importante porque a honestidade do registro depende da segurança que o paciente sente ao escrevê-lo, e nem tudo que ele anota precisa ou deve ser compartilhado.

O paciente também tem acesso, no seu perfil, a análises geradas automaticamente sobre seus próprios padrões — resumos semanais, identificação de temas recorrentes, correlações entre eventos e estados emocionais — que servem como ferramenta de autoconhecimento e reflexão. Tem ainda acesso a um modo de apoio em momentos difíceis, com recursos imediatos de orientação, técnicas de respiração e contatos de emergência.

## Como Funciona — Visão do Psicólogo

O psicólogo acessa o MoodTrack com um perfil profissional. No painel principal, ele visualiza sua lista de pacientes vinculados e tem acesso a um conjunto de ferramentas pensadas para enriquecer e organizar sua prática clínica.

Para cada paciente, o psicólogo encontra o histórico organizado das sessões realizadas e agendadas. Sessões podem ser agendadas com recorrência, gerando automaticamente os espaços onde o profissional fará suas anotações. Ao entrar no card de uma sessão específica, o psicólogo registra observações no modelo que preferir — texto livre ou estruturado em campos como queixa principal, intervenções aplicadas, hipóteses clínicas e plano para a próxima sessão.

A plataforma também oferece transcrição automática de sessões, caso o psicólogo escolha gravá-las com autorização do paciente. A transcrição é organizada e pode ser revisada, anotada e arquivada junto ao prontuário daquela sessão.

Antes de cada nova sessão, o psicólogo recebe um briefing automaticamente preparado pela plataforma, sintetizando o que aconteceu desde o último encontro: quantos registros o paciente fez, qual a tendência geral do humor no período, quais temas apareceram com maior frequência, quais escalas foram respondidas e como evoluíram, e quais pontos podem merecer atenção na conversa. Esse briefing economiza tempo de preparação e ajuda o profissional a entrar na sessão melhor informado.

Ao longo do tratamento, o psicólogo pode visualizar uma linha do tempo terapêutica que combina, em formato cronológico, todos os elementos relevantes: registros do paciente, sessões realizadas, escalas respondidas, eventos importantes que o paciente registrou. Essa visualização funciona como um prontuário visual, ajudando o profissional a perceber padrões e construir uma narrativa clara do percurso do paciente.

O psicólogo também pode prescrever ao paciente atividades terapêuticas — exercícios de registro de pensamentos, técnicas de respiração, tarefas de observação — que aparecem no aplicativo do paciente como sugestões a serem realizadas e devolvidas, fechando o ciclo entre sessão e prática.

## A Camada de Inteligência Artificial

A inteligência artificial no MoodTrack tem um papel claramente definido: ela é uma ferramenta de apoio ao trabalho do psicólogo e ao autoconhecimento do paciente, nunca uma substituta do trabalho clínico humano. A plataforma não oferece terapia automatizada, não dá conselhos clínicos diretos ao paciente e não toma decisões em lugar do profissional.

A IA atua em quatro frentes principais. Primeiro, na transcrição de áudios — tanto das gravações de sessão (quando autorizadas) quanto das anotações em áudio que o paciente faz no seu dia a dia, transformando fala em texto pesquisável e organizável. Segundo, na análise de padrões dos dados do paciente — identificando temas recorrentes, mudanças de tendência no humor, correlações entre eventos e estados emocionais, e marcando no texto possíveis distorções cognitivas que merecem atenção do profissional. Terceiro, na geração de resumos e briefings — produzindo sínteses semanais ou pré-sessão que economizam tempo do psicólogo e oferecem ao paciente devolutivas sobre seus próprios padrões. Quarto, no sistema de alertas — identificando situações que merecem atenção imediata, como sinais de risco ou padrões preocupantes sustentados ao longo do tempo, e notificando o profissional para que ele possa agir clinicamente.

Toda análise gerada pela IA é apresentada como apoio interpretativo, não como diagnóstico ou conclusão. O psicólogo permanece como o agente clínico responsável, e o paciente recebe os insights como material para reflexão própria, sempre com a recomendação clara de buscar suporte profissional quando necessário.

## Ética, Privacidade e Proteção de Dados

O MoodTrack lida com informações de natureza profundamente íntima. Registros de saúde mental, pensamentos pessoais, relatos de sessões terapêuticas e gravações de áudio constituem dados sensíveis no sentido mais estrito do termo — material que, se exposto indevidamente, pode causar danos reais à vida das pessoas. Reconhecer essa responsabilidade é o ponto de partida do projeto, não uma preocupação secundária.

A primeira camada de cuidado está no consentimento. Ao se cadastrar, o paciente passa por um processo de consentimento granular, no qual cada finalidade de uso dos seus dados é apresentada de forma separada e clara, em linguagem acessível, sem juridiquês. O paciente decide, em itens distintos, se aceita compartilhar seus registros com o psicólogo vinculado, se aceita que seus dados sejam processados pela inteligência artificial para gerar análises e resumos, se aceita receber lembretes e notificações da plataforma. Cada uma dessas autorizações pode ser revogada a qualquer momento, sem que isso implique a exclusão da conta inteira ou a perda de funcionalidades não relacionadas. O psicólogo, ao se cadastrar como profissional, também passa por um termo próprio que estabelece suas responsabilidades como cuidador dos dados dos seus pacientes dentro da plataforma.

A segunda camada está no controle de visibilidade. Como mencionado anteriormente, cada registro do paciente carrega uma decisão explícita sobre o compartilhamento com o psicólogo. Isso significa que o paciente nunca é forçado a compartilhar tudo para usar a plataforma — ele pode manter um espaço genuinamente privado, ao mesmo tempo em que compartilha o que considera relevante para o tratamento. Essa decisão é fundamental para a integridade do produto: um diário onde o paciente sente que está sendo observado deixa de ser um diário honesto, e um diário desonesto perde valor terapêutico.

A terceira camada é a proteção técnica dos dados. Todas as informações trafegam de forma criptografada entre o aplicativo e os servidores, e ficam armazenadas de forma criptografada também em repouso. Os campos mais sensíveis — anotações pessoais, transcrições de sessão, gravações de áudio, registros de pensamentos — recebem uma camada adicional de proteção que impede que mesmo administradores da plataforma consigam ler esse conteúdo diretamente. O acesso aos dados é estritamente limitado ao vínculo terapêutico autorizado: um psicólogo só vê os pacientes que estão vinculados a ele, e essa regra é aplicada de forma rigorosa em todas as operações da plataforma. Todo acesso a dados sensíveis é registrado em um histórico de auditoria, garantindo que, em caso de qualquer questionamento, seja possível rastrear quem acessou o quê e quando.

A quarta camada diz respeito ao processamento pelos sistemas de inteligência artificial. Antes de qualquer dado do paciente ser enviado para análise por modelos de IA, ele passa por um processo de descaracterização: nomes próprios, locais específicos, instituições, datas e outros elementos que poderiam identificar diretamente o paciente ou pessoas mencionadas por ele são substituídos por marcadores genéricos. Esse processo reduz significativamente a exposição dos dados, e a correspondência entre o original e a versão descaracterizada fica guardada em um cofre separado e protegido, acessível apenas para que os resultados da análise possam ser apresentados de volta ao psicólogo de forma compreensível. Além disso, a plataforma utiliza serviços de IA configurados para não reter os dados processados nem utilizá-los para treinamento de modelos, mantendo o controle das informações sob a gestão da plataforma e do paciente.

A quinta camada são os direitos do titular dos dados. O paciente, a qualquer momento, pode acessar tudo o que a plataforma tem armazenado sobre ele, baixar essas informações em formato compreensível, corrigir registros que contenham erros, revogar consentimentos previamente dados ou solicitar a exclusão completa da sua conta e de todos os dados associados. Essas operações são realizadas diretamente pelo próprio usuário, sem necessidade de solicitar a alguém da plataforma, e são executadas em prazos curtos.

Por fim, a plataforma reconhece com clareza seus limites. O MoodTrack não é uma ferramenta de atendimento de emergência. Em situações de crise, o paciente é direcionado imediatamente para canais especializados, como serviços de apoio em saúde mental e telefones de emergência reconhecidos. A plataforma orienta de forma constante que o cuidado profissional humano é insubstituível e que a tecnologia tem o papel de apoiar, organizar e qualificar esse cuidado, nunca de assumi-lo.

## Princípios Norteadores

Quatro princípios orientam todas as decisões do MoodTrack:

1. **Cuidado humano em primeiro lugar.** A tecnologia serve à relação terapêutica, não a substitui. Toda funcionalidade é avaliada pela pergunta: isso melhora o cuidado clínico humano que o paciente recebe?
2. **Autonomia do paciente.** O paciente é dono dos seus dados, das suas decisões de compartilhamento, do seu ritmo de uso. A plataforma oferece estrutura, mas não impõe caminhos.
3. **Apoio ao profissional.** O psicólogo recebe ferramentas que economizam tempo administrativo, organizam informação e qualificam decisões — liberando energia para o que realmente importa, que é o trabalho clínico em si.
4. **Responsabilidade com dados sensíveis.** Cada decisão técnica e de produto é tomada considerando que os dados manipulados são profundamente íntimos, e que a confiança depositada pelos usuários é o ativo mais valioso da plataforma.

## Resumo

O MoodTrack é uma plataforma de acompanhamento da saúde mental que conecta psicólogos e pacientes em um ambiente seguro, oferecendo registro estruturado do cotidiano emocional, ferramentas de organização clínica, análises automatizadas de padrões e apoio inteligente à prática terapêutica — tudo isso construído sobre uma base sólida de consentimento informado, controle granular de privacidade, proteção técnica de dados sensíveis e respeito absoluto à autonomia e à dignidade dos seus usuários.