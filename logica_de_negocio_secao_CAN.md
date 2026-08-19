# Contexto: Quando recebemos o material, recebemos de uma seção chamada CAN, que também deveria ter conferido os materiais e recebidos antes de no entregar. Vamos expandir o Concan para essa seção, para que larguem a papelada e fiquem com o serviço mais automatizado. No geral é que eles tenham um sistema independente, mas que possam rastrear o que nós fazemos, onde o contrário também é verdade. Os operadores do CAN não conseguem operar no ConCAN da seção de recebimento (Seção em que eu trabalho) e os operadores do recebimento não conseguem operar no ConCAN da seção CAN. Cada operador de uma seção pode APENAS rastrear as atividades da outra seção, mas nunca interagir com a operação da outra seção. Os únicos dados compartilhados são os Manifestos, que são os documentos principais que contém as informações de todos os materiais que devem ser conferidos, fora isso, a barra de carregamento de conferência de cada manifesto é individual por seção, logo a conferência da TSRE terá um progresso, enquanto a do CAN terá seuu próprio progresso, conforme usa conferência também.

# Devem haver indicadores, tal como um check ao lado do número de manifesto, indicando se já foi conferido pelo CAN, 2 checks se foi conferido pelo CAN e pelo Recebimento e um círculo se só tiver sido recebido pelo recebimento. Essa separação é importante, pois não podemos garantir que o CAN terá a disciplina de sempre fazer a inclusão de manifestos e conferência, dito isso, precisamos saber quando conferiram ou não.

# Todo manifesto incluso deve ser salvo e deve poder ser baixado a qualquer momento, garantindo que a qualquer momento possamos ter o manifesto completo. O processo deve ser exatamente igual ao da TSRE, exceto pela ausência do filtro de volumes destinados somente ao PAMALS, pois o CAN recebe todos os volumes destinados às OMs de Lagoa Santa, e os destinam, seja ao CIAAR, PALS, GAP-LS, etc. Enquanto o PAMA-LS recebe só os do PAMA LS, que é o que tem um filtro já ativo, conforme acontece no projeto em produção


1 - Criar perfil usuário CAN
2 - Criar tela de recebimento para a seção CAN
3 - Criar extração de dados de manifesto sem filtro para a seção CAN
4 - Confirmação de Recebimento na TSRE, pós conferência da seção CAN
5 - Verificação de status de recebimento do material por seção de trabalho
6 - Rastreabilidade total entre seções
7 - Seperação de atividades por seção / Divergência de operadores
8 - Isolamento de operações (CAN / TSRE)
9 - Volumes retirados in loco no CAN ou não recebidos, viram OBS no ConCAN do recebimento, para posterior verificação
10 - Todos os manifestos escaneados e extraídos devem ser acessíveis na íntegra, de forma que, o manifesto incluído possa ser baixado e verificado na íntegra, para os casos em que não incluirem um volume posterior no manifesto e não atualizarem no concan
11 - Criar rastreabilidade do manifesto, de forma que todos saibam quem incluiu o manifesto no sistema.
12 - O acesso à tela da seção de recebimento pela seção CAN, será restrito apenas pela visualização dos dados, não podendo interagir com a operação.
13 - O acesso à outra seção será através do "3 pontinhos" que abrem as opções de configuração ou outras opções, sendo denominado "CAN" como a seção CAN e "TSRE" como a seção de recebimento
14 - O manifesto é compartilhado: quem faz o primeiro upload 'publica' o PDF para ambas as seções. Sugiro que todo manifesto ao ser conferido pelo CAN, deve ficar como pendente para a TSRE, de forma que a TSRE decida se esse manifesto vai de fato ser conferido por nós ou não, para que manifestos que não devam ser conferidos, não fiquem enchendo a tela de manifestos que já existem hoje
15 - A sincronização com o Sheets não se aplica ao CAN no momento
16 - Deve haver o perfil de super-admin que gerencia as 2 seções, e o perfil de "Admin TSRE" e "Admin CAN", que somente podem gerenciar suas respectivas seções, mas não podem apagar usuários ou acessar a configuração da outra seção
17 - O modo OCR ainda está em desenvolvimento, por isso não vai ser herdado
18 - A aparência do APP não vai variar por usuário
19 - Os requisitos acima devem ser seguidos, e ser separados em fases por ordem de complexidade, onde cada fase vai abordar o máximo de tópicos possíveis, de forma que a IA que vai construir, consiga fazê-la sem muita dficuldade, tal como uma fase com 3 inclusões simples, ou uma fase com 1 inclusão complexa.
20 - Todos os dados já existentes no banco devem ser atribuídos automaticamente à seção TSRE
21 - Mantenha um único registro, mas o manifesto que for incluído pelo CAN deve ser autorizado ou negado por algum usuário da TSRE que ele apareça na nossa tela. O inverso deve acontecer com os manifestos da TSRE que devem ser autorizados por algum usuário do CAN para aparecer na nossa tela. Caso seja negado, o manifesto poderá ser incluído depois manualmente pela TSRE. Caso já exista no CAN, não aparecerá para eles
22 - Caso a TSRE faça o 1° download, para a TSRE há o filtro de apenas para o PAMALS, mas se o can for autorizar, ele verá todos os destinatários na integra
23 - A exclusão de manifesto terá escopo de seção
24 - O Super-Admin pode fazer tudo, inclusive mexer com usuários
25 - A tabela de logs deve ser separa por seção
26 - Os volumes extramanifestos podem ser vistos pela TSRE, caso incluidos pelo can, e vice-versa, mas não podem ser incluídos por usuários da outra seção. Ou seja, um usuário TSRE não pode incluir um volume extra manifesto para o CAN, e vice-versa
27 - Quando o usuário CAN clicar em TSRE no menu, ele será direcionado para uma versão somente-leitura do dashboard da TSRE. Exatamente o que acontece na TSRE, só que agora no CAN, onde o usuário TSRE terá acesso apenas à visualização da tela, não podendo interagir com a operação