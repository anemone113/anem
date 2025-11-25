// editor.js


// 5) Управление редактором и 3) Отображение заметок
export const Editor = {
    
    // Инициализация кнопок редактора (цвета и фокус)
    initToolbar() {
        const buttons = document.querySelectorAll('.toolbar button');
        const editor = document.getElementById('note-text');

        buttons.forEach(btn => {
            // Предотвращаем потерю фокуса при клике на кнопку
            btn.onmousedown = (e) => {
                e.preventDefault();
                const command = btn.dataset.command;
                const arg = btn.dataset.arg || null;
                document.execCommand(command, false, arg);
                this.updateToolbarStatus(); // Обновляем цвет сразу
            };
        });

        // Слушаем события внутри редактора, чтобы менять подсветку кнопок
        editor.addEventListener('keyup', () => this.updateToolbarStatus());
        editor.addEventListener('mouseup', () => this.updateToolbarStatus());
        editor.addEventListener('click', () => this.updateToolbarStatus());
    },

    updateToolbarStatus() {
        const buttons = document.querySelectorAll('.toolbar button');
        buttons.forEach(btn => {
            const command = btn.dataset.command;
            // Проверяем, активен ли стиль (bold, italic) в текущей позиции курсора
            if (document.queryCommandState(command)) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    },

    // 3) Рендер вертикального списка заметок в плеере
    renderMiniTimeline(notes, currentEpisode, onEdit, onDelete) {
        const container = document.getElementById('player-timeline');
        container.innerHTML = '';

        // Фильтрация по текущей серии (если серия выбрана)
        // Если currentEpisode === null (фильм), показываем всё, у чего нет серии или episode === null
        // Если currentEpisode есть, показываем только заметки этой серии
        const filteredNotes = notes.filter(n => {
            if (currentEpisode) return n.episode === currentEpisode;
            return !n.episode; // Показываем заметки фильма/общего
        });

        // Сортировка: от ранних к поздним
        filteredNotes.sort((a, b) => {
            // Превращаем HH:MM:SS в секунды для сравнения (упрощенно по строке тоже работает, если формат строгий)
            return a.timestamp.localeCompare(b.timestamp);
        });

        filteredNotes.forEach(note => {
            const div = document.createElement('div');
            div.className = 'mini-note';

            // Обрезаем текст до 1 строки
            let previewText = note.text.replace(/<[^>]*>/g, '').trim(); // убрать html теги
            if (previewText.length === 0 && note.hasImage) previewText = "[Фото]";
            else if (note.hasImage) previewText = `[Фото] ${previewText}`;
            
            // Защита от длинного текста
            // CSS text-overflow сделает '...', но на всякий случай
            
            const timeSpan = `<div class="mini-note-time">${note.timestamp}</div>`;
            const textSpan = `<div class="mini-note-text">${previewText || 'Без текста'}</div>`;
            
            const infoDiv = document.createElement('div');
            infoDiv.className = 'mini-note-info';
            infoDiv.innerHTML = timeSpan + textSpan;
            infoDiv.onclick = () => onEdit(note); // Клик открывает редактор

            const delBtn = document.createElement('button');
            delBtn.className = 'btn-icon';
            delBtn.innerHTML = '🗑';
            delBtn.onclick = (e) => {
                e.stopPropagation(); // Чтобы не открылся редактор
                if(confirm('Удалить заметку?')) onDelete(note.id);
            };

            div.appendChild(infoDiv);
            div.appendChild(delBtn);
            container.appendChild(div);
        });
    }
};
