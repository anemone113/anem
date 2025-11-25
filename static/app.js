// app.js (Обновленный)

import { Timer } from './timer.js';
import { Editor } from './editor.js';
import { HistoryApp } from './history.js';

const tg = window.Telegram.WebApp;
tg.expand();

// Настройки
const USER_ID = tg.initDataUnsafe?.user?.id || '6217936347'; // Работаем под ID 12345

const state = {
    // ... ваши старые поля
    mediaId: null,      
    title: "",
    episodes: [],       
    currentEpisode: null, 
    notes: [],          
    editingNoteId: null,
    
// НОВОЕ ПОЛЕ: Хранит ID картинок, которые УЖЕ есть в базе у текущей заметки
    currentNoteImages: [],
    // ← ДОБАВИТЬ СЮДА
    creatingMedia: false,
    
    // 💡 ДОБАВИТЬ ЭТО ПОЛЕ
    previousScreen: 'screen-menu' 
};

let editorLiveTimerInterval = null;
const Notify = {
    timeout: null,

    show(text, type = 'info') {
        const el = document.getElementById('save-status');

        el.className = 'save-status show';
        el.innerText = text;

        if (type === 'success') el.classList.add("success");
        else if (type === 'error') el.classList.add("error");

        el.classList.remove("hidden");

        clearTimeout(this.timeout);
        this.timeout = setTimeout(() => {
            el.classList.remove("show");
            setTimeout(() => {
                el.classList.add("hidden");
                el.classList.remove("success", "error");
            }, 300);
        }, 2000);
    }
};


const App = {
    uploadedFiles: [],

    init() {
        // --- Автосохранение названия при вводе ---
        let titleTypingTimer = null;
        const titleInput = document.getElementById('media-title');

        titleInput.oninput = (e) => {
            clearTimeout(titleTypingTimer);
            titleTypingTimer = setTimeout(() => {
                App.ensureMediaCreated(e.target.value);
            }, 400); // debounce 400мс
        };

        // --- Дополнительно сохраняем при потере фокуса ---
        titleInput.onchange = (e) => {
            App.ensureMediaCreated(e.target.value);
        };

        // --- Таймер ---
        Timer.init((timeString) => {
            document.getElementById('timer').innerText = timeString;
        });

        Editor.initToolbar();

        document.getElementById('btn-timer-toggle').onclick = () => this.toggleTimer();
        document.getElementById('btn-timer-reset').onclick = () => Timer.reset();
        document.getElementById('btn-timer-edit').onclick = () => this.editTimerTime();
    },
    continueWatchingFromHistory() {
        if (!HistoryApp.currentMedia) {
            Notify.show("Нет выбранной записи для продолжения.", "error");
            this.showScreen('screen-menu');
            return;
        }

        // 1. Получаем данные из HistoryApp
        const mediaToContinue = HistoryApp.currentMedia;

        // 2. Вызываем toNewView с этими данными
        // Экрану screen-player нужны эти данные для state
        this.toNewView(mediaToContinue);
        
        // 3. (Опционально) Обновляем поле названия в UI
        document.getElementById('media-title').value = mediaToContinue.title;
        
        // 4. Показываем экран плеера
        this.showScreen('screen-player');
    },

    toEditorView(existingNote = null) {
        // --- НЕ сбрасываем mediaId, title, episodes, notes! ---
        Timer.reset();

        const noteTime = existingNote ? existingNote.timestamp : Timer.formatTime();
        document.getElementById('editor-timestamp').innerText = noteTime;

        // 💡 НОВОЕ: ЗАПОМИНАЕМ, ОТКУДА ПРИШЛИ
        const activeScreen = document.querySelector('.screen.active');
        state.previousScreen = activeScreen ? activeScreen.id : 'screen-menu';

        const noteArea = document.getElementById('note-text');
        noteArea.innerHTML = existingNote ? existingNote.text : "";

        // Очистка превью
        const container = document.getElementById('preview-container');
        container.innerHTML = "";
        this.uploadedFiles = [];
        state.currentNoteImages = [];

        // Если существующая заметка — подгружаем картинки
        if (existingNote) {
            let ids = existingNote.file_ids || [];
            if (existingNote.file_id && ids.length === 0) ids = [existingNote.file_id];
            state.currentNoteImages = ids;

            ids.forEach(fid => {
                const img = document.createElement('img');
                img.src = `/api/media/get_image_url?file_id=${fid}`; // или fetch для динамического URL
                img.className = 'preview-thumb';
                container.appendChild(img);
            });
        }

        // Настройка таймера для редактирования
        const liveLabel = document.getElementById("editor-timer-live");
        const pauseBtn = document.getElementById("editor-timer-pause");

        if (Timer.isRunning) {
            liveLabel.style.display = "inline";
            pauseBtn.style.display = "inline-block";

            editorLiveTimerInterval = setInterval(() => {
                liveLabel.innerText = `(текущий: ${Timer.formatTime()})`;
            }, 1000);

            pauseBtn.onclick = () => {
                Timer.stop();
                pauseBtn.style.display = "none";
            };
        } else {
            liveLabel.style.display = "none";
            pauseBtn.style.display = "none";
            clearInterval(editorLiveTimerInterval);
            editorLiveTimerInterval = null;
        }

        state.editingNoteId = existingNote ? existingNote.id : null;
        this.showScreen('screen-editor');
    },




    openQuickTagMenu() {
        if (!state.title?.trim()) {
            alert("Пожалуйста сначала укажите название");
            return;
        }
        document.getElementById("quick-tag-menu").style.display = "flex";
    },

    closeQuickTagMenu() {
        document.getElementById("quick-tag-menu").style.display = "none";
    },

    async addQuickTag(textTemplate) {
        this.closeQuickTagMenu();

        const timestamp = Timer.formatTime();
        const episode = state.currentEpisode;

        // Убеждаемся, что media создано
        const mediaId = await this.ensureMediaCreated();
        if (!mediaId) {
            alert("Ошибка: медиа не создано");
            return;
        }

        const payload = {
            user_id: USER_ID,
            media_id: mediaId,
            text: `Быстрая метка: ${textTemplate}`,
            timestamp: timestamp,
            episode: episode,
            file_id: null
        };

        try {
            const res = await fetch('/api/timer/add_entry', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });

            const data = await res.json();

            if (data.status === "success") {
                // Обновляем локальный список заметок
                state.notes.push({
                    id: data.entry_id,
                    text: payload.text,
                    timestamp: timestamp,
                    episode: episode,
                    file_id: null
                });

                this.renderNotesTimeline();
            } else {
                alert("Ошибка сохранения");
            }
        } catch (e) {
            console.error(e);
            alert("Ошибка связи с сервером");
        }
    },
    // --- Вспомогательная функция: Гарантирует, что Media создано в БД ---
    async ensureMediaCreated(titleOverride = null) {
        const newTitle = titleOverride || state.title || ("Новая запись " + new Date().toLocaleDateString());

        // --- Если запись существует: обновляем название ---
        if (state.mediaId) {
            if (newTitle !== state.title) {
                try {
                    Notify.show("Сохраняю название...");
                    await fetch('/api/timer/update_media_title', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            user_id: USER_ID,
                            media_id: state.mediaId,
                            title: newTitle
                        })
                    });
                    state.title = newTitle;
                    Notify.show("Название сохранено!", "success");
                } catch (e) {
                    console.error("Ошибка обновления названия:", e);
                    Notify.show("Ошибка сохранения", "error");
                }
            }
            return state.mediaId;
        }
        // ---- ПРЕДОТВРАЩАЕМ ДУБЛИ ----
        if (state.creatingMedia) return null;
        state.creatingMedia = true;
        // --- Создание нового media ---
        try {
            Notify.show("Создаю запись...");
            const res = await fetch('/api/timer/create_media', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    user_id: USER_ID,
                    title: newTitle,
                    type: state.episodes.length > 0 ? 'series' : 'movie'
                })
            });
            const data = await res.json();

            if (data.status === 'success') {
                state.mediaId = data.media_id;
                state.title = newTitle;
                console.log("Media created with ID:", state.mediaId);
                Notify.show("Создано!", "success");
                return state.mediaId;
            }
        } catch (e) {
            console.error("Error creating media:", e);
            alert("Ошибка связи с сервером");
        }
        return null;
    },

    // --- Навигация ---
    showScreen(id) {
        document.querySelectorAll('.screen').forEach(el => el.classList.remove('active'));
        document.getElementById(id).classList.add('active');
    },

    toMenu() {
        Timer.stop();
        this.updatePlayButton();
        this.showScreen('screen-menu');
    },

// app.js

    toNewView(mediaData = null) {
        // Сброс состояния, только если это ДЕЙСТВИТЕЛЬНО новый просмотр
        if (!mediaData) {
            state.mediaId = null;
            state.title = "";
            state.episodes = [];
            state.currentEpisode = null;
            state.notes = [];
            state.editingNoteId = null;
            Timer.reset();
        } else {
            // Инициализация существующими данными
            state.mediaId = mediaData.id;
            state.title = mediaData.title;
            state.episodes = mediaData.episodes || [];
            state.currentEpisode = mediaData.currentEpisode || null;
            state.notes = mediaData.entries || []; // 'entries' это заметки из базы
            state.editingNoteId = null; // Сбрасываем ID заметки, которую редактировали
            
            // Если в данных есть последняя позиция (например, `mediaData.last_position`), 
            // можно инициализировать таймер
            // Timer.setSeconds(mediaData.last_position || 0);
            
            // Важно: если мы продолжаем просмотр, запускаем таймер с 0 или с последней позиции
            Timer.reset(); 
        }

        document.getElementById('media-title').value = state.title || "";
        this.renderEpisodes();
        this.renderNotesTimeline();
        this.showScreen('screen-player');
    },


    // --- Логика Плеера ---
    updateTitle(val) {
        state.title = val;
    },

    addEpisode() {
        let num = state.episodes.length + 1;
        state.episodes.push(`Серия ${num}`);
        if (state.episodes.length === 1) this.selectEpisode(`Серия ${num}`);
        else this.renderEpisodes();
    },

    selectEpisode(epName) {
        state.currentEpisode = epName;
        this.renderEpisodes();
        this.renderNotesTimeline();
    },

    renderEpisodes() {
        // ... (Ваш код рендера эпизодов без изменений) ...
        const section = document.getElementById('episode-section');
        const list = document.getElementById('episode-list');
        list.innerHTML = '';

        if (state.episodes.length === 0) {
            section.style.display = 'none';
            return;
        }
        section.style.display = 'block';

        let movieChip = document.createElement('div');
        movieChip.className = `chip ${state.currentEpisode === null ? 'active' : ''}`;
        movieChip.innerText = "Общее / Фильм";
        movieChip.onclick = () => this.selectEpisode(null);
        list.appendChild(movieChip);

        state.episodes.forEach(ep => {
            let chip = document.createElement('div');
            chip.className = `chip ${state.currentEpisode === ep ? 'active' : ''}`;
            chip.innerText = ep;
            chip.onclick = () => this.selectEpisode(ep);
            list.appendChild(chip);
        });
    },

    // --- Таймер ---
    toggleTimer() {
        Timer.toggle();
        this.updatePlayButton();
    },
    updatePlayButton() {
        document.getElementById('btn-timer-toggle').innerText = Timer.isRunning ? '⏸ Пауза' : '▶ Старт';
    },
    editTimerTime() {
        let val = prompt("Время (ЧЧ:ММ:СС, например 01:22:14)", "0");
        if(val) Timer.setSeconds(Timer.parseInput(val));
    },

    // --- Редактор и Сохранение ---
    // --- Замени свою старую функцию openEditor на эту ---
    async openEditor(existingNote = null) {
        if (!state.title?.trim()) {
            alert("Пожалуйста сначала укажите название");
            return;
        }
        // 💡 НОВОЕ: ЗАПОМИНАЕМ, ОТКУДА ПРИШЛИ
        const activeScreen = document.querySelector('.screen.active');
        state.previousScreen = activeScreen ? activeScreen.id : 'screen-menu';

        state.editingNoteId = existingNote ? existingNote.id : null;
        const timeVal = existingNote ? existingNote.timestamp : Timer.formatTime();
        document.getElementById('editor-timestamp').innerText = timeVal;
        
        const noteArea = document.getElementById('note-text');
        noteArea.innerHTML = existingNote ? existingNote.text : "";
        
        // Очистка
        const container = document.getElementById('preview-container');
        container.innerHTML = ""; 
        this.uploadedFiles = [];
        state.currentNoteImages = []; // Сброс списка старых картинок

        this.showScreen('screen-editor');

        // ЛОГИКА ЗАГРУЗКИ КАРТИНОК
        if (existingNote) {
            // Нормализация: превращаем старый file_id в массив или берем file_ids
            let ids = existingNote.file_ids || [];
            if (existingNote.file_id && ids.length === 0) {
                ids = [existingNote.file_id];
            }

            state.currentNoteImages = ids; // Запоминаем текущие ID

            if (ids.length > 0) {
                const loadingLabel = document.createElement('div');
                loadingLabel.innerText = `Загрузка фото (${ids.length})...`;
                loadingLabel.style.fontSize = "12px";
                loadingLabel.id = 'loading-lbl';
                container.appendChild(loadingLabel);

                // Загружаем превью для каждого ID параллельно
                Promise.all(ids.map(async (fid) => {
                    try {
                        const res = await fetch(`/api/media/get_image_url?file_id=${fid}`);
                        const data = await res.json();
                        if (data.url) return { url: data.url, id: fid };
                    } catch (e) { console.error(e); }
                    return null;
                })).then(results => {
                    if(document.getElementById('loading-lbl')) container.removeChild(loadingLabel);
                    
                    results.forEach(item => {
                        if(item) {
                            // Создаем контейнер для фото (чтобы можно было потом добавить кнопку удаления)
                            let wrapper = document.createElement('div');
                            wrapper.className = 'img-wrapper';
                            wrapper.style.display = 'inline-block';
                            wrapper.style.position = 'relative';
                            wrapper.style.margin = '5px';

                            let img = document.createElement('img');
                            img.src = item.url;
                            img.className = 'preview-thumb';
                            
                            wrapper.appendChild(img);
                            container.appendChild(wrapper);
                        }
                    });
                });
            }
        };
        // --- Новая часть про таймер во время редактирования ---
        const liveLabel = document.getElementById("editor-timer-live");
        const pauseBtn = document.getElementById("editor-timer-pause");

        // Если таймер сейчас работает — показываем текущий
        if (Timer.isRunning) {
            liveLabel.style.display = "inline";
            pauseBtn.style.display = "inline-block";

            // Обновляем каждые 1000 мс
            editorLiveTimerInterval = setInterval(() => {
                liveLabel.innerText = `(текущий: ${Timer.formatTime()})`;
            }, 1000);

            // функционал кнопки паузы
            pauseBtn.onclick = () => {
                Timer.stop();
                pauseBtn.style.display = "none";
            };
        } else {
            // Таймер не идёт — ничего не показываем
            liveLabel.style.display = "none";
            pauseBtn.style.display = "none";
            clearInterval(editorLiveTimerInterval);
            editorLiveTimerInterval = null;
        }        
    },

    handleFiles(input) {
        // ... (Код превью картинок без изменений) ...
        const files = Array.from(input.files);
        const container = document.getElementById('preview-container');
        files.forEach(file => {
            this.uploadedFiles.push(file);
            let reader = new FileReader();
            reader.onload = (e) => {
                let img = document.createElement('img');
                img.src = e.target.result;
                img.className = 'preview-thumb';
                container.appendChild(img);
            };
            reader.readAsDataURL(file);
        });
    },

    async saveNote() {
        clearInterval(editorLiveTimerInterval);
        editorLiveTimerInterval = null;
        if (!state.title?.trim()) {
            alert("Пожалуйста сначала укажите название");
            return;
        }        
        const text = document.getElementById('note-text').innerHTML;
        const timestamp = document.getElementById('editor-timestamp').innerText;
        
        const saveBtn = document.querySelector('.toolbar button[data-command="save"]');
        if(saveBtn) saveBtn.disabled = true;

        try {
            Notify.show("Сохраняю заметку...");
            const mediaId = await this.ensureMediaCreated();
            if (!mediaId) throw new Error("Media ID creation failed");

            // 1. ЗАГРУЗКА НОВЫХ ФАЙЛОВ
            let newFileIds = [];
            
            if (this.uploadedFiles.length > 0) {
                console.log(`Начинаю загрузку ${this.uploadedFiles.length} изображений...`);
                
                // Создаем массив промисов для параллельной загрузки
                const uploadPromises = this.uploadedFiles.map(async (file) => {
                    const formData = new FormData();
                    formData.append('image', file);
                    formData.append('user_id', USER_ID);
                    
                    try {
                        const res = await fetch('/api/media/upload_image', {
                            method: 'POST',
                            body: formData
                        });
                        const data = await res.json();
                        if (data.status === 'success') return data.file_id;
                    } catch (e) {
                        console.error("Ошибка загрузки файла:", e);
                    }
                    return null;
                });

                // Ждем пока все загрузятся
                const results = await Promise.all(uploadPromises);
                newFileIds = results.filter(id => id !== null); // Убираем ошибки
            }

            // 2. ОБЪЕДИНЕНИЕ ID (Старые + Новые)
            // Мы берем те, что уже были (state.currentNoteImages) и добавляем новые
            const finalFileIds = [...state.currentNoteImages, ...newFileIds];

            // 3. ФОРМИРОВАНИЕ ЗАПРОСА
            const payload = {
                user_id: USER_ID,
                media_id: mediaId,
                text: text,
                timestamp: timestamp,
                episode: state.currentEpisode,
                file_ids: finalFileIds // Отправляем массив!
            };

            let res;
            // РЕДАКТИРОВАНИЕ
            if (state.editingNoteId && String(state.editingNoteId).length > 5) { 
                payload.entry_id = state.editingNoteId;
                res = await fetch('/api/timer/update_entry', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
            } 
            // СОЗДАНИЕ
            else {
                res = await fetch('/api/timer/add_entry', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
            }

            const data = await res.json();
            
            if (data.status === 'success') {
                this.uploadedFiles = [];
                document.getElementById('preview-container').innerHTML = "";
                document.getElementById('note-text').innerHTML = "";
                state.currentNoteImages = [];

                Notify.show("Заметка сохранена!", "success");
                // Передаем массив ID для обновления UI
                this.refreshUIAfterSave(data.key || state.editingNoteId, text, timestamp, finalFileIds);
            } else {
                alert("Ошибка при сохранении заметки в БД");
                Notify.show("Ошибка сохранения", "error");
            }
        } catch (e) {
            console.error(e);
            alert("Произошла ошибка: " + e.message);
        } finally {
            if(saveBtn) saveBtn.disabled = false;
        }
    },
    // Вынес обновление интерфейса в отдельный метод для чистоты
        refreshUIAfterSave(noteId, text, timestamp, fileIds) {
            // Логика обновления списка заметок (timeline)
            const newNoteLocal = {
                id: noteId,
                text, 
                timestamp, 
                episode: state.currentEpisode, 
                // hasImage true, если массив не пустой
                hasImage: (fileIds && fileIds.length > 0), 
                file_ids: fileIds || []      // Сохраняем массив
            };
            
            if (state.editingNoteId) {
                 const idx = state.notes.findIndex(n => n.id === state.editingNoteId);
                 if(idx !== -1) state.notes[idx] = { ...state.notes[idx], ...newNoteLocal };
            } else {
                state.notes.push(newNoteLocal);
            }
            
            this.renderNotesTimeline();
            this.cancelEditor();
        },
    async deleteNote(noteId) {

        // Если это локальная заметка (еще не отправлена - редкий кейс, но все же)
        if (!state.mediaId) {
            state.notes = state.notes.filter(n => n.id !== noteId);
            this.renderNotesTimeline();
            return;
        }

        try {
            const res = await fetch(`/api/timer/delete_entry?user_id=${USER_ID}&media_id=${state.mediaId}&entry_id=${noteId}`, {
                method: 'DELETE'
            });
            const data = await res.json();
            if (data.status === 'success') {
                state.notes = state.notes.filter(n => n.id !== noteId);
                this.renderNotesTimeline();
            }
        } catch (e) {
            alert('Ошибка удаления');
        }
    },
    toggleHistory() {
        const listScreen = document.getElementById('screen-list');

        // Если список уже открыт — закрываем (как кнопка ←)
        if (listScreen.classList.contains('active')) {
            this.toMenu();
        } 
        // Если нет — открываем
        else {
            this.toHistory();
        }
    },
    renderNotesTimeline() {
        Editor.renderMiniTimeline(
            state.notes, 
            state.currentEpisode, 
            (note) => this.openEditor(note), 
            (id) => this.deleteNote(id)
        );
    },

    cancelEditor() {
        clearInterval(editorLiveTimerInterval);
        editorLiveTimerInterval = null;      
        
        // 💡 ИСПРАВЛЕНИЕ: ВОЗВРАЩАЕМСЯ НА ЭКРАН, С КОТОРОГО ПЕРЕШЛИ
        // Если это screen-view (история), то возвращаемся на screen-player,
        // Иначе возвращаемся на то, что сохранили, или по умолчанию на screen-player
        let screenToReturn;
        if (state.previousScreen === 'screen-view' && HistoryApp.currentMedia) {
             // Если мы пришли с экрана просмотра записи (истории), 
             // то нас интересует возврат в режим "Продолжить просмотр" (screen-player)
             screenToReturn = 'screen-player';
        } else if (state.previousScreen === 'screen-player') {
             // Если мы пришли с экрана плеера - туда и возвращаемся
             screenToReturn = 'screen-player';
        } else {
             // Если пришли откуда-то еще (напр., редактировали старую заметку из истории)
             // или state.previousScreen не установлен - возвращаемся в меню
             screenToReturn = 'screen-menu';
        }

        // Сбрасываем ID редактируемой заметки
        state.editingNoteId = null;

        this.showScreen(screenToReturn);

        // ВАЖНО: Если возвращаемся на screen-player, то нужно возобновить таймер, 
        // если он не был принудительно остановлен в редакторе
        if (screenToReturn === 'screen-player' && Timer.wasRunning) {
            Timer.start();
            this.updatePlayButton();
        }
    },
    
    // --- Связь с модулем History ---
    toHistory() { Timer.stop(); HistoryApp.init('view'); },
    toEditMode() { Timer.stop(); HistoryApp.init('edit'); },
    
    // Вызывается из HistoryApp для редактирования старой заметки
    openEditorFromHistory(noteId) {
        const note = HistoryApp.currentMedia.entries.find(n => n.id == noteId);
        if (note) {
            state.mediaId = HistoryApp.currentMedia.id;
            state.currentEpisode = note.episode;

            // Приводим к массиву file_ids, если старый формат
            if (note.file_id && !note.file_ids) {
                note.file_ids = [note.file_id];
            }

            this.toEditorView(note);
        }
    }

};

window.app = App;
window.timer = Timer; 
App.init();