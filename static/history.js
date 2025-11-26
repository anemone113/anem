// history.js

const API_BASE = '/api';

const tg = window.Telegram.WebApp;

const FALLBACK_USER_ID = '6217936347';

function getCurrentUserId() {
    // 1. Получаем ID из Telegram
    const tgUserId = tg?.initDataUnsafe?.user?.id;

    if (tgUserId) {
        return tgUserId.toString();
    }

    // 2. Пробуем получить ID из URL (если вдруг используешь через браузер)
    const urlParams = new URLSearchParams(window.location.search);
    const userIdFromUrl = urlParams.get('user_id');
    if (userIdFromUrl) {
        return userIdFromUrl;
    }

    // 3. Фоллбек для локального тестирования
    console.warn("User ID not found. Using fallback ID:", FALLBACK_USER_ID);
    return FALLBACK_USER_ID;
}

const CURRENT_USER_ID = getCurrentUserId();



function formatDate(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    return d.toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    }).replace(',', '');
}

function timeToSeconds(timeStr) {
    if (!timeStr) return 0;
    const parts = timeStr.split(':').map(Number);
    let seconds = 0;
    if (parts.length === 3) seconds = parts[0] * 3600 + parts[1] * 60 + parts[2];
    else if (parts.length === 2) seconds = parts[0] * 60 + parts[1];
    return seconds;
}

export const HistoryApp = {
    data: [], 
    currentMode: 'view', 
    currentMedia: null,
    currentEpisode: null,
    
    // Для галереи
    galleryQueue: [],
    galleryIndex: 0,

    async init(mode) {
        this.currentMode = mode;
        this.currentMedia = null;
        this.currentEpisode = null;
        
        document.getElementById('list-title').innerText = mode === 'edit' ? 'Редактирование' : 'История просмотров';
        document.getElementById('screen-view').classList.remove('active');
        document.getElementById('screen-list').classList.add('active');
        
        // Скрываем кнопку действий при инициализации
        this.toggleFloatingButton(false);
        
        await this.loadData();
    },

    // --- Управление плавающей кнопкой удаления (Пункт 2) ---
    toggleFloatingButton(show, text = "Удалить выбранное", action = null) {
        let btn = document.getElementById('floating-delete-btn');
        
        // Создаем кнопку, если её нет в DOM
        if (!btn) {
            btn = document.createElement('div');
            btn.id = 'floating-delete-btn';
            btn.style.cssText = `
                position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
                background: #ff4444; color: white; padding: 12px 24px;
                border-radius: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                font-weight: bold; cursor: pointer; z-index: 1000; display: none;
                transition: transform 0.2s, opacity 0.2s;
            `;
            document.body.appendChild(btn);
        }

        if (show) {
            btn.innerText = text;
            btn.onclick = action;
            btn.style.display = 'block';
            // Небольшая анимация
            requestAnimationFrame(() => btn.style.transform = 'translateX(-50%) scale(1)');
        } else {
            btn.style.display = 'none';
            btn.style.transform = 'translateX(-50%) scale(0.9)';
        }
    },


    // Генерируем ссылку.
    openShareModal() {
        if (!this.currentMedia) return;

         
        // Если это Telegram WebApp, window.location.href может быть специфичным, 
        // но обычно window.location.origin + window.location.pathname работает для веба.
        // Мы добавляем параметры owner_id и shared_media_id
        
        const baseUrl = `${window.location.origin}${window.location.pathname}`;
        const shareUrl = `${baseUrl}?owner_id=${CURRENT_USER_ID}&shared_media_id=${this.currentMedia.id}`;

        const input = document.getElementById('share-link-input');
        input.value = shareUrl;

        document.getElementById('share-modal').style.display = 'flex';
    },

    // 2. Метод копирования ссылки
    copyShareLink() {
        const input = document.getElementById('share-link-input');
        input.select();
        input.setSelectionRange(0, 99999); // Для мобильных
        
        try {
            document.execCommand('copy');
            alert('Ссылка скопирована!');
            document.getElementById('share-modal').style.display = 'none';
        } catch (err) {
            alert('Не удалось скопировать автоматически');
        }
    },

    // 3. ПРОВЕРКА РЕЖИМА ГОСТЯ (Shared Mode)
    async checkSharedLink() {
        const urlParams = new URLSearchParams(window.location.search);
        const ownerId = urlParams.get('owner_id');
        const mediaId = urlParams.get('shared_media_id');

        if (ownerId && mediaId) {
            console.log("Режим гостя активирован:", ownerId, mediaId);
            await this.loadSharedMedia(ownerId, mediaId);
            return true; // Возвращаем true, чтобы остановить обычную загрузку
        }
        return false;
    },

    // 4. Загрузка чужого медиа
    async loadSharedMedia(ownerId, mediaId) {
        // Показываем экран просмотра сразу
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        document.getElementById('screen-view').classList.add('active');
        document.getElementById('view-timeline').innerHTML = '<div style="text-align:center; padding:20px;">Загрузка общего таймлайна...</div>';

        try {
            // Используем новый API endpoint
            const res = await fetch(`${API_BASE}/timer/get_one?user_id=${ownerId}&media_id=${mediaId}`);

            const text = await res.text();
            console.log("RAW RESPONSE:", text);

            let data;
            try {
                data = JSON.parse(text);
            } catch (parseErr) {
                console.error("JSON parse ERROR:", parseErr);
                alert("Ошибка загрузки ссылки: сервер вернул не JSON");
                return;
            }

            if (data.error) throw new Error(data.error);

            // Превращаем entries из объекта в массив (как в loadData)
            if (data.entries && typeof data.entries === 'object' && !Array.isArray(data.entries)) {
                data.entries = Object.keys(data.entries).map(k => ({ id: k, ...data.entries[k] }));
            }

            this.currentMedia = data;
            
            // Настройка UI для гостя
            document.getElementById('view-title').innerText = `(Гость) ${this.currentMedia.title}`;
            
            // Скрываем кнопки управления, так как гость не может менять чужое
            const btnContinue = document.getElementById('btn-continue-watching');
            if (btnContinue) btnContinue.style.display = 'none';
            
            const btnShare = document.getElementById('btn-share');
            if (btnShare) btnShare.style.display = 'none'; // Гость не может шерить чужое (или может, если хотите)

            // Скрываем кнопку "Назад", если мы пришли сразу по ссылке, 
            // или меняем её действие на "Перейти в своего бота"
            // Для простоты оставим как есть, она вернет в (пустой) список или главное меню
            
            this.renderEpisodeChips();
            this.selectEpisode(null);

        } catch (e) {
            console.error(e);
            alert("Ошибка загрузки ссылки: " + e.message);
            // Если ошибка, кидаем в меню
            document.getElementById('screen-view').classList.remove('active');
            document.getElementById('screen-menu').classList.add('active');
        }
    },

    // Функция проверки чекбоксов для обновления кнопки
    updateSelectionState(type) {
        const selector = type === 'media' ? '.media-checkbox:checked' : '.entry-checkbox:checked';
        const checkedCount = document.querySelectorAll(selector).length;
        
        if (checkedCount > 0) {
            const action = type === 'media' ? () => this.deleteSelectedMedia() : () => this.deleteSelectedEntries();
            this.toggleFloatingButton(true, `Удалить ${checkedCount}`, action);
        } else {
            this.toggleFloatingButton(false);
        }
    },

    async loadData() {
        // ... (Ваш код загрузки данных без изменений) ...
        // Для краткости я его свернул, но он должен быть здесь
        const container = document.getElementById('list-container');
        container.innerHTML = '<div style="text-align:center; padding:20px;">Загрузка...</div>';
        
        try {
            const res = await fetch(`${API_BASE}/timer/get_all?user_id=${CURRENT_USER_ID}`);
            const json = await res.json();
            
            let rawData = json.timers || json;

            if (rawData && typeof rawData === 'object' && !Array.isArray(rawData)) {
                this.data = Object.keys(rawData).map(key => ({ id: key, ...rawData[key] }));
            } else {
                this.data = rawData || [];
            }

            this.data.forEach(media => {
                if (media.entries && typeof media.entries === 'object' && !Array.isArray(media.entries)) {
                    media.entries = Object.keys(media.entries).map(k => ({ id: k, ...media.entries[k] }));
                }
            });

            this.data.sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0));

            this.renderList();
        } catch (e) {
            console.error("Load Data Error:", e);
            container.innerHTML = `<div style="color:red; text-align:center;">Ошибка: ${e.message}</div>`;
        }
    },

    // --- Рендер списка произведений (Уровень 1) ---
    renderList() {
        const container = document.getElementById('list-container');
        container.innerHTML = '';
        this.toggleFloatingButton(false); // Сброс кнопки

        if (!this.data || this.data.length === 0) {
            container.innerHTML = '<div style="text-align:center; color:#777;">Пусто</div>';
            return;
        }

        this.data.forEach(media => {
            const el = document.createElement('div');
            el.className = 'list-item';
            
            // ПУНКТ 4: Чекбоксы рядом с названиями произведений
            el.style.display = 'flex';
            el.style.alignItems = 'center';
            el.style.gap = '10px';

            let checkboxHtml = '';
            if (this.currentMode === 'edit') {
                checkboxHtml = `
                    <div onclick="event.stopPropagation()" style="display:flex; align-items:center;">
                        <input type="checkbox" class="media-checkbox" data-id="${media.id}" 
                               style="transform: scale(1.3); margin-right: 5px;"
                               onchange="window.historyApp.updateSelectionState('media')">
                    </div>`;
            }

            const lastUpdate = media.entries && media.entries.length > 0 
                ? media.entries[media.entries.length-1].timestamp 
                : '';

            el.innerHTML = `
                ${checkboxHtml}
                <div class="list-info" style="flex: 1;">
                    <h4>${media.title}</h4>
                    <p>
                        ${media.type === 'movie' ? 'Фильм' : 'Сериал'} • 
                        <span style="opacity: 0.7;">${formatDate(media.created_at)}</span>
                    </p>
                </div>
            `;
            
            // Клик по строке открывает произведение
            el.onclick = () => window.historyApp.openMedia(media.id);

            container.appendChild(el);
        });
    },

    // --- Удаление выбранных произведений (Пункт 4) ---
    async deleteSelectedMedia() {
        const checked = document.querySelectorAll('.media-checkbox:checked');
        if (checked.length === 0) return;

        if (!confirm(`Удалить выбранные произведения (${checked.length})?`)) return;

        const idsToDelete = Array.from(checked).map(cb => cb.getAttribute('data-id'));
        
        // Удаляем каждое произведение
        for (const id of idsToDelete) {
             await this.deleteMedia(id, false); // false = без перерисовки на каждом шаге
        }
        
        // Обновляем UI один раз в конце
        this.renderList();
    },

    // Модифицированный deleteMedia
    async deleteMedia(mediaId, shouldRender = true) {
        // Оптимистичное удаление из локальных данных
        this.data = this.data.filter(m => m.id !== mediaId);
        
        if (shouldRender) this.renderList();

        try {
            await fetch(`${API_BASE}/timer/delete?user_id=${CURRENT_USER_ID}&media_id=${mediaId}`, { method: 'DELETE' });
        } catch (e) {
            console.error("Ошибка удаления на сервере", e);
        }
    },


    openMedia(mediaId) {
        this.currentMedia = this.data.find(m => m.id === mediaId);
        if (!this.currentMedia) return;

        document.getElementById('screen-list').classList.remove('active');
        document.getElementById('screen-view').classList.add('active');
        document.getElementById('view-title').innerText = this.currentMedia.title;
        
        this.toggleFloatingButton(false); // Скрываем кнопку из списка
        this.renderEpisodeChips();
        this.selectEpisode(null);
        
        // Скрываем/показываем контролы если нужно, но у нас теперь логика через чекбоксы
        const editControls = document.getElementById('edit-controls');
        if(editControls) editControls.style.display = 'none'; 
    },

    renderEpisodeChips() {
        // ... (Без изменений, код тот же) ...
        const container = document.getElementById('view-episodes');
        container.innerHTML = '';
        const episodes = new Set();
        (this.currentMedia.entries || []).forEach(e => { if (e.episode) episodes.add(e.episode); });
        
        if (episodes.size === 0) {
            container.style.display = 'none';
            return;
        }
        container.style.display = 'flex';
        const allChip = document.createElement('div');
        allChip.className = 'chip active';
        allChip.innerText = 'Всё';
        allChip.onclick = () => this.selectEpisode(null, allChip);
        container.appendChild(allChip);
        episodes.forEach(ep => {
            const chip = document.createElement('div');
            chip.className = 'chip';
            chip.innerText = ep;
            chip.onclick = () => this.selectEpisode(ep, chip);
            container.appendChild(chip);
        });
    },

    selectEpisode(epName, clickedChip) {
        this.currentEpisode = epName;
        if (clickedChip) {
            document.querySelectorAll('#view-episodes .chip').forEach(c => c.classList.remove('active'));
            clickedChip.classList.add('active');
        }
        this.renderTimeline();
    },

    // --- Рендер таймлайна (Уровень 3) ---
    renderTimeline() {

        const container = document.getElementById('view-timeline');
        container.innerHTML = '';
        this.toggleFloatingButton(false);

        let entries = this.currentMedia.entries || [];

        if (this.currentEpisode) {
            entries = entries.filter(e => e.episode === this.currentEpisode);
        }

        entries.sort((a, b) => timeToSeconds(a.timestamp) - timeToSeconds(b.timestamp));

        if (entries.length === 0) {
            container.innerHTML = '<div style="text-align:center; padding:40px; color:#666;">Заметок нет</div>';
            return;
        }

        entries.forEach((entry, index) => {

            const row = document.createElement('div');
            row.className = 'timeline-row';

            // Раскладка
            let gapHeight = 30;
            if (index < entries.length - 1) {
                const currentSec = timeToSeconds(entry.timestamp);
                const nextSec = timeToSeconds(entries[index + 1].timestamp);
                const diff = nextSec - currentSec;
                if (diff > 0) gapHeight = Math.min(150, 30 + (Math.sqrt(diff) * 3));
            }

            let wrapperStart = '';
            let wrapperEnd = '';
            let checkboxHtml = '';

            if (this.currentMode === 'edit') {

                wrapperStart = `<div style="display: flex; flex-direction: row; align-items: flex-start; width: 100%;">`;

                checkboxHtml = `
                    <div style="padding-top: 5px; margin-right: 10px; flex-shrink: 0;">
                        <input type="checkbox" class="entry-checkbox" data-id="${entry.id}" 
                               style="transform: scale(1.3);"
                               onchange="window.historyApp.updateSelectionState('entries')">
                    </div>
                `;
                wrapperEnd = `</div>`;
            }

            // Сбор медиа
            const fileIds = Array.isArray(entry.file_ids)
                ? entry.file_ids
                : (entry.file_id ? [entry.file_id] : []);

            let mediaHtml = '';
            if (fileIds.length > 0) {
                mediaHtml = `<div class="media-grid">`;
                fileIds.forEach((fid, idx) => {
                    mediaHtml += `<img src="" data-src="${fid}" class="media-thumb" onclick="event.stopPropagation(); historyApp.openImageModal(['${fileIds.join("','")}'], ${idx})">`;
                });
                mediaHtml += `</div>`;
                this.lazyLoadImages(fileIds);
            }

            // CLICK ACTION → ключевой кусок
            const entryFileIds = fileIds;
            const fileIdsString = JSON.stringify(entryFileIds).replace(/"/g, '&quot;');

            const clickAction = this.currentMode === 'edit'
                ? `window.app.openEditorFromHistory('${entry.id}')`
                : `historyApp.openTextModal(\`${(entry.text || '').replace(/`/g, "\\`").replace(/"/g, "&quot;")}\`, ${fileIdsString})`;

            console.log("👉 [Entry] clickAction:", clickAction);

            row.innerHTML = `
                <div class="timeline-body">
                    ${wrapperStart} ${checkboxHtml}
                        <div class="timeline-card" style="flex: 1;" 
                             onclick="${clickAction}">
                            <div class="truncated-text">
                                ${entry.text || '<em style="color:#555">Без текста</em>'}
                            </div>
                            ${mediaHtml}
                        </div>
                    ${wrapperEnd} </div>

                <div class="timeline-axis">
                    <div class="time-pill">${entry.timestamp}</div>
                    <div class="timeline-line" style="height: ${gapHeight}px;"></div>
                </div>
            `;

            container.appendChild(row);

        });
        this.applyImageSources();
    },

    // --- Удаление выбранных заметок (Пункт 2 - логика) ---
    async deleteSelectedEntries() {
        const checked = document.querySelectorAll('.entry-checkbox:checked');
        if (checked.length === 0) return;
        
        const idsToDelete = Array.from(checked).map(cb => cb.getAttribute('data-id'));
        if(!confirm(`Удалить выбранные заметки (${idsToDelete.length})?`)) return;

        // Удаляем из локального массива UI
        this.currentMedia.entries = this.currentMedia.entries.filter(e => !idsToDelete.includes(String(e.id)));
        
        // Обновляем интерфейс
        this.renderTimeline();

        // Отправляем запросы на сервер (поштучно, т.к. массового API нет, но это работает)
        for (const noteId of idsToDelete) {
            try {
                await fetch(`${API_BASE}/timer/delete_entry?user_id=${CURRENT_USER_ID}&media_id=${this.currentMedia.id}&entry_id=${noteId}`, {
                    method: 'DELETE'
                });
            } catch(e) { console.error(e); }
        }
    },
    
    async lazyLoadImages(fileIds) {}, // (заглушка для краткости, используйте свой код)
    
    async applyImageSources() {
         const imgs = document.querySelectorAll('.media-thumb[data-src]');
         imgs.forEach(async (img) => {
             const fileId = img.getAttribute('data-src');
             if (!img.getAttribute('src')) {
                 try {
                     const res = await fetch(`${API_BASE}/media/get_image_url?file_id=${fileId}`);
                     const data = await res.json();
                     if (data.url) img.src = data.url;
                 } catch(e) { }
             }
         });
    },

    openTextModal(text, fileIds = []) {
        const body = document.getElementById('modal-body');
        document.getElementById('modal-nav').style.display = 'none';

        let mediaHtml = '';
        if (fileIds.length > 0) {
            mediaHtml = `
                <hr style="border-color: #333; margin: 15px 0;">
                <div class="media-grid media-grid-modal">
            `;
            fileIds.forEach((fid, idx) => {
                // Используем openImageModal для показа полноразмерного изображения
                mediaHtml += `<img src="" data-src="${fid}" class="media-thumb" 
                                    onclick="event.stopPropagation(); historyApp.openImageModal(['${fileIds.join("','")}'], ${idx})">`;
            });
            mediaHtml += `</div>`;
        }

        body.innerHTML = `
            <div class="full-text">${text}</div>
            ${mediaHtml}
        `;
        // Сначала делаем модальное окно видимым
        document.getElementById('media-modal').style.display = 'flex';
        
        // Затем, в следующем цикле событий (чтобы дать DOM обновиться), запускаем загрузку изображений
        setTimeout(() => {
            if (fileIds.length > 0) {
                this.applyImageSources(); 
            }
        }, 0); 
    },
    

    openImageModal(fileIds, startIndex) {
        this.galleryQueue = fileIds;
        this.galleryIndex = startIndex;
        
        document.getElementById('modal-nav').style.display = (fileIds.length > 1) ? 'flex' : 'none';
        document.getElementById('media-modal').style.display = 'flex';
        
        this.showSlide(this.galleryIndex);
    },

    async showSlide(index) {
        if (index < 0) index = this.galleryQueue.length - 1;
        if (index >= this.galleryQueue.length) index = 0;
        this.galleryIndex = index;

        const body = document.getElementById('modal-body');
        body.innerHTML = '<div style="color:white">Загрузка...</div>';
        document.getElementById('slide-counter').innerText = `${index+1}/${this.galleryQueue.length}`;

        const fileId = this.galleryQueue[index];
        // Запрос URL
        try {
            const res = await fetch(`${API_BASE}/media/get_image_url?file_id=${fileId}`);
            const data = await res.json();
            if (data.url) {
                body.innerHTML = `<img src="${data.url}" class="full-image">`;
            }
        } catch(e) { body.innerHTML = 'Error'; }
    },

    nextSlide() { this.showSlide(this.galleryIndex + 1); },
    prevSlide() { this.showSlide(this.galleryIndex - 1); },
    
    closeModal() {
        document.getElementById('media-modal').style.display = 'none';
    },



    backToList() {
        document.getElementById('screen-view').classList.remove('active');
        document.getElementById('screen-list').classList.add('active');
        this.currentMedia = null;
        this.currentEpisode = null;
        this.renderList(); 
    },
    async deleteMedia(mediaId) {
        // Оптимистичное обновление интерфейса (сразу убираем из списка)
        const oldData = [...this.data];
        this.data = this.data.filter(m => m.id !== mediaId);
        this.renderList();

        try {
            const res = await fetch(`${API_BASE}/timer/delete?user_id=${CURRENT_USER_ID}&media_id=${mediaId}`, {
                method: 'DELETE'
            });
            const d = await res.json();
            if (d.status !== 'success') {
                throw new Error("Server error");
            }
        } catch (e) {
            alert("Ошибка удаления, возвращаем данные.");
            this.data = oldData;
            this.renderList();
        }
    },
    async deleteSelected() {
        const checked = document.querySelectorAll('.edit-checkbox:checked');
        if (checked.length === 0) return alert("Ничего не выбрано");
        
        const idsToDelete = Array.from(checked).map(cb => cb.getAttribute('data-id'));
        
        if(!confirm(`Удалить ${idsToDelete.length} заметок?`)) return;

        
        // Имитация удаления из UI
        this.currentMedia.entries = this.currentMedia.entries.filter(e => !idsToDelete.includes(String(e.id)));
        this.renderTimeline();
    },
};

window.historyApp = HistoryApp;

