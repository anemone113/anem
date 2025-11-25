// timer.js

export const Timer = {
    seconds: 0,
    interval: null,
    isRunning: false,
    onUpdate: null, // Callback функция для обновления UI

    init(updateCallback) {
        this.onUpdate = updateCallback;
    },

    start() {
        if (this.isRunning) return;
        this.isRunning = true;
        this.interval = setInterval(() => {
            this.seconds++;
            if(this.onUpdate) this.onUpdate(this.formatTime());
        }, 1000);
    },

    stop() {
        this.isRunning = false;
        clearInterval(this.interval);
    },

    toggle() {
        return this.isRunning ? this.stop() : this.start();
    },

    reset() {
        this.stop();
        this.seconds = 0;
        if(this.onUpdate) this.onUpdate(this.formatTime());
    },

    setSeconds(sec) {
        this.seconds = sec;
        if(this.onUpdate) this.onUpdate(this.formatTime());
    },

    // 4) Время всегда указывается как ЧЧ:ММ:СС
    formatTime() {
        const h = Math.floor(this.seconds / 3600).toString().padStart(2, '0');
        const m = Math.floor((this.seconds % 3600) / 60).toString().padStart(2, '0');
        const s = (this.seconds % 60).toString().padStart(2, '0');
        return `${h}:${m}:${s}`;
    },
    formatTimeFromSeconds(sec) {
        const h = Math.floor(sec / 3600).toString().padStart(2, '0');
        const m = Math.floor((sec % 3600) / 60).toString().padStart(2, '0');
        const s = (sec % 60).toString().padStart(2, '0');
        return `${h}:${m}:${s}`;
    },
    parseInput(val) {
        if (!val) return 0;
        if (val.includes(":")) {
            let parts = val.split(":");
            if (parts.length === 3) {
                return parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(parts[2]);
            } else {
                return parseInt(parts[0]) * 60 + parseInt(parts[1]);
            }
        }
        return parseInt(val);
    }
};
