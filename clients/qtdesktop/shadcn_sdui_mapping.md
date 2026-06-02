# Mapping Completo Componenti Shadcn/UI vs SDUI Democrai

Questo documento consolida sistematicamente tutti i componenti presenti in [shadcn/ui](https://ui.shadcn.com/docs/components) per tracciare una roadmap definitiva della nostra implementazione **Server-Driven UI (SDUI)** su PySide6/Qt. 

👉 **Focus sul Data Binding (Populator):** Oltre alle definizioni base, viene qui specificato in modo esplicito **quali parametri/collezioni** hanno maggior senso logico per essere esposti al motore di Binding (es. `$state.var`, `$global.my_list`) per rendere il frontend reattivo.

👉 **Focus Architetturale (DataTable & Form):** Sono annesse le analisi critiche su bottleneck e roadmap di refactoring necessarie per convertire i due asset più vitali (Forms e Tabelle) allo standard enterprise B2B.

---

## 🧭 Navigazione e Struttura

### 1. Tabs
*   **Parametri:** `tabs` (lista di id/label), `default_tab`, `variant`.
*   **Logica Populator (Data Binding):** 
    *   **⚡ Populator Ideale:** `tabs = $state.my_dynamic_tabs`. Molto utile in contesti in cui i tab variano in base ai permessi o a selezioni precedenti senza dover re-inviare il layout.
    *   **Stato Selezionato:** `$state.current_tab`.
*   **Modalità Operative:** Statica (figli nel JSON originario) vs Dinamica (Routing-based proxyata al server).
*   **Priorità:** **Alta**.

### 2. Accordion / Collapsible
*   **Logica Populator:** L'intero array di `accordion_items` popolato da `$state.log_entries` o `$state.faq_list`. Utile se si espande live al variare dei log.
*   **Stato Aperto:** `$state.accordion_{id}_open`.
*   **Priorità:** **Alta**.

### 3. Sidebar (App Navigation)
*   **Logica Populator:** `items = $global.user_menu`. Permette di mutare il menu contestualmente allo switch di workspace.
*   **Priorità:** **Media/Risolto**.

### 4. Breadcrumb
*   **Logica Populator:** `segments = $state.current_path_segments`. Il Breadcrumb si aggiorna reattivamente al variare del navigation state, evitando il refetch dell'header.
*   **Priorità:** **Media**.

---

## 📝 Form, Input e Controlli

### Macro-Componente: Form Builder (forms.py)
Il Form Builder è il cuore degli applicativi. Attualmente molto solido ma va scalato.
*   **🔴 Criticità Attuali (Bottlenecks):**
    *   **Monolite Inseparabile:** Impossibile usare una `Select` fuori da un tag `Form` (ad es. in una Navbar), perché i rendering widget sono annidati.
    *   **Layout Rigidissimo:** `width=100%` in pila (QVBoxLayout), impossibile avere nome/cognome affiancati.
    *   **Validazione solo Client:** Manca il binding profondo per iniettare l'errore asincrono del server nel field corrispondente senza un ricaricamento.
    *   **Interdipendenze:** Manca il binding di visibilità condizionale (es. mostrare campo IVA solo se type="Azienda").
*   **🟢 Roadmap Refactoring:**
    *   Smembramento in `InputRenderer`, `SelectRenderer`, ecc., tutti autonomi. Il Form diventa un semplice wrapper di raccolta stato.
    *   Introduzione del **FormGrid** con attributi `span: 6` su griglia a 12 colonne per supportare campi multi-riga combinati.
    *   Aggiunta binding errori: il Form ascolta su `$state.form_errors.email` e accende lo stato rosso solo dell'input corretto reattivamente.
    *   Parametro generico `visible_if: "$state.company == true"` inseribile in ogni Renderer SDUI.

### 5. Select / Combobox
*   **Logica Populator:** `options = $state.country_list` o `$global.users_list`. Permette opzioni condivise senza appesantire il JSON.
*   **Priorità:** **Alta** (da astrarre fuori dal blocco Form). È fondamentale il `Combobox` (select con search built-in per 10k opzioni).

### 6. Switch & Checkbox
*   **Logica Populator:** `$state.form_data.is_enabled`.
*   **Priorità:** **Alta**. Rendering ottico dello Switch stile iOS/Shadcn da implementare per soppiantare il Checkbox base nei toggle.

### 7. Date Picker / Calendar
*   **Logica Populator:** `min_date = $state.booking_start` vincola la data fine in base alla scelta precedente in tempo reale.
*   **Priorità:** **Alta**.

---

## 📊 Visualizzazione e Componenti Strutturati

### 8. Data Table / Table (datatable.py)
Ottimo per casi base, le feature inline sono solide, ma soffre se diamo in pasto enormi array.
*   **Logica Populator:** `rows = $state.table_data` (ottimo, già implementato). Idea: `columns = $state.user_columns` per far scegliere i layout all'utente e salvarli a DB.
*   **🔴 Criticità Attuali (Bottlenecks):**
    *   Usa `QTableWidget` a memoria fissa: ripopolare interamente lo stato su 3.000 righe frizzerà `1-2s` il thread primario UI (blocco event loop).
    *   Modifica/Delete hardcoded in bottoni separati (spazio eccessivo).
    *   Manca selezione e bulk execution. Manca sorting bidirezionale cliccando gli header collegati via Actions SDUI.
*   **🟢 Roadmap Refactoring:**
    *   **Priorità Media/Alta (Fase 2):** Migrazione a Modello **Virtualizzato MVC** (`QTableView` + `QAbstractTableModel`). Garantisce caricamento `O(1)` indipendentemente dalle size dello state.
    *   Menu **Tre Puntini (Dropdown)** per ospitare dinamicamente multiple Row Actions senza sfondare l'UI di pulsanti.
    *   Selezione Checkbox con injection del payload listato nella main Table Action.
    *   Loading overlay mask locale sulla tabella quando scatta Pagination.

### 9. Badge
*   **Logica Populator:** `text = $state.status_label` e `variant = $state.status_color_class`. Rende super reattivo cambiare uno status rosso/verde senza reinviare UI via server, ma inviando una patch state JSON leggerissima.
*   **Priorità:** **Alta**.

### 10. Skeleton / Progress
*   **Logica Populator:** `is_loading = $state.fetching_users`. 
*   **Priorità:** **Alta**. È un must visualmente mostrare un "pulse ghost" prima dell'arrivo UI.

---

## 🪟 Overlays, Feedback Modali e Menu

### 11. Dropdown Menu / Context Menu
*   **Logica Populator:** `items = $state.context_actions`. Generato on-demand al click dell'utente.
*   **Priorità:** **Alta**. Irrinunciabile, sopratutto connesso alle righe DataTable.

### 12. Alert
*   **Logica Populator:** Binding al flag `$state.has_errors` (per mostrare/nascondere il blocco d'errore generale sopra una form) e `message = $state.global_error_text`.
*   **Priorità:** **Alta**.

### 13. Dialog / Toast (Sonner)
*   **Priorità:** **Risolti in Desktop core Shell**. Attivati tendenzialmente via signal/action imperative.

---

## 🤖 AI & Conversational UI (Assistant-UI)

Per gestire chat complesse, agenti autonomi e thread conversazionali in Democrai (Fase 2, layer Agenti AI e RAG), l'integrazione dei pattern definiti da [assistant-ui](https://www.assistant-ui.com/docs/ui/thread) è cruciale. 

Qui la mappatura dei loro componenti core verso i nostri populator Qt/SDUI:

### 14. Thread (Root & Viewport)
*   **Parametri:** `autoScroll` (bool).
*   **Logica Populator:** Wrapper principale. Il `Viewport` ascolta in tempo reale la lunghezza dello `$state.chat_messages` e gestisce l'auto-scroll verso il basso all'arrivo di nuovi token.
*   **Priorità:** **Alta**. Requisito fondamentale per la Killer App.

### 15. Messages List & Message Item
*   **Parametri:** `role` (user, assistant, system). Supporto per layout asimmetrici (User a dx, Assistant a sx).
*   **Logica Populator:** 
    *   **⚡ Populator Ideale:** `messages = $state.active_thread_history`. 
    *   Gestione nativa dello streaming: I messaggi in arrivo ("Assistant") si arricchiscono testualmente ascoltando pacchetti Delta dello state senza reinviare l'intero history.
*   **Azioni:** `on_edit`, `on_delete`, `on_copy`.
*   **Priorità:** **Alta**. Il renderer può fare re-use massivo del nostro `MarkdownRenderer` esistente.

### 16. Composer (Input Bar)
*   **Parametri:** `placeholder`, `disabled`, `multiline`.
*   **Logica Populator:** Il testo composto è bindato a `$state.draft_message`.
*   **Azioni:** `on_send` invia la query al backend LLM/Agent. `on_cancel` interrompe lo stream in corso.
*   **Aspetto:** Barra di input fissa in fondo (fixed bottom), simile all'input group ma con auto-grow in altezza e bottoni d'azione integrati (Send, Attach File, Stop).
*   **Priorità:** **Alta**.

### 17. ThreadList (Sidebar History)
*   **Parametri:** `threads` (lista di conversazioni storiche).
*   **Logica Populator:** `items = $state.user_threads_list`. Simile alla Navigation Sidebar ma specializzata nel mostrare snippet, data aggiornamento e indicatori ("Nuova Risposta").
*   **Azioni:** Cliccare cambia il `$state.active_thread_id` ricaricando l'intero Thread Root.
*   **Priorità:** **Media**.
 
### 18. Suggestions / Quick Replies
*   **Parametri:** `suggestions` (array di prompts testuali).
*   **Logica Populator:** Iniettate dinamicamente dall'Agente a fine messaggio (`$state.current_suggestions`). Utile per guidare flussi utente complessi.
*   **Azioni:** Cliccare un Suggestion lo lancia direttamente nel Composer e fa dispatch del `on_send`.
*   **Priorità:** **Media**.

### 19. ScrollToBottom Button
*   **Parametri:** Variabile visibilità calcolata sulla base dello scroll position.
*   **Priorità:** **Bassa/UI Detail**. Rende l'esperienza dell'utente molto reattiva se si perde su lunghi wall of text di RAG.
