==============
Odoo Generator
==============

Questa applicazione effettua il download dei sorgenti Odoo e prepara un virtualenv.

Pre-requisiti:

.. code-block:: bash

    sudo apt install libmysqlclient-dev

.. code-block:: bash

    curl https://pyenv.run | bash
    echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
    echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
    echo 'eval "$(pyenv init -)"' >> ~/.bashrc

Per usare questa funzionalità, eseguire:

.. code-block:: bash

    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ./main/odoogenerator.py --version[-V] 14.0 [--private|-P yes]

Questo creerà nella cartella `Sviluppo` dell'utente corrente una cartella `Odoo` con una sotto-cartella `odoo<versione>` in cui verrà installato Odoo alla versione presente nella configurazione e creato un file di configurazione `.odoorc`

La configurazione è nella cartella dell'utente `./Sviluppo/srvmngt/odoogenerator_config` e si compone di due file:

#. un file txt con i requirements aggiuntivi specifici (i requirements di Odoo sono già installati di default, oltre a quelli di l10n-italy, da verificare se installare anche quelli delle altre repositories)
#. un file json con le specifiche per l'installazione.

Ci sono delle opzioni alternative di avvio:

Con il tag aggiuntivo `-S yes` viene solo generato il file `.odoorc` nella cartella della versione selezionata:

.. code-block:: bash

    -S

Con il tag aggiuntivo `-T <repository>` vengono aggiornati i file di traduzione all'interno dei moduli nella cartella del repository della versione selezionata:

.. code-block:: bash

    -T <repository>

Con il tag aggiuntivo `-G ['yes' | 'no]` viene eseguito il gitaggregate dei repository durante la generazione, in modo da avere il codice aggiornato con le PR impostate nel file :

.. code-block:: bash

    -G yes