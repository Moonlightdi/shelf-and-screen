// Sound generation and parts of this file written with help from Claude.
// ♪ The music of a book: a little music box made from the colors of its cover.
// Used on the book page and on the blind date page.
(function() {
    // Pentatonic scales: every note sounds good with every other note
    const MAJOR = [0, 2, 4, 7, 9];
    const MINOR = [0, 3, 5, 7, 10];
    const MUSIC = {
        dark: { scale: MINOR, base: 57, step: 0.75, third: 3 },
        warm: { scale: MAJOR, base: 60, step: 0.45, third: 4 },
        calm: { scale: MAJOR, base: 62, step: 0.6, third: 4 },
        soft: { scale: MAJOR, base: 67, step: 0.55, third: 4 },
    };

    let audio = null;
    let stopTimer = null;
    let whenDone = null;

    function styleFor(moodName) {
        moodName = moodName || "";
        if (moodName.includes("dark")) return MUSIC.dark;
        if (moodName.includes("calm")) return MUSIC.calm;
        if (moodName.includes("soft")) return MUSIC.soft;
        return MUSIC.warm;
    }

    function hexToHueLight(hex) {
        const r = parseInt(hex.slice(1, 3), 16) / 255;
        const g = parseInt(hex.slice(3, 5), 16) / 255;
        const b = parseInt(hex.slice(5, 7), 16) / 255;
        const max = Math.max(r, g, b);
        const min = Math.min(r, g, b);
        const light = (max + min) / 2;
        let hue = 0;
        if (max !== min) {
            const d = max - min;
            if (max === r) hue = ((g - b) / d) % 6;
            else if (max === g) hue = (b - r) / d + 2;
            else hue = (r - g) / d + 4;
            hue = (hue * 60 + 360) % 360;
        }
        return { hue: hue, light: light };
    }

    function midiToFrequency(midi) {
        return 440 * Math.pow(2, (midi - 69) / 12);
    }

    // hue -> which note of the scale, light colors -> one octave higher
    function colorToMidi(hex, style) {
        const c = hexToHueLight(hex);
        const index = Math.floor(c.hue / 360 * style.scale.length) % style.scale.length;
        const octave = c.light > 0.7 ? 12 : 0;
        return style.base + style.scale[index] + octave;
    }

    // one soft music-box note: a pure tone plus quiet higher overtones
    function bell(frequency, start, output) {
        [[1, 0.5], [2, 0.12], [3, 0.04]].forEach(function(part) {
            const osc = audio.createOscillator();
            const gain = audio.createGain();
            osc.type = "sine";
            osc.frequency.value = frequency * part[0];
            gain.gain.setValueAtTime(0, start);
            gain.gain.linearRampToValueAtTime(part[1], start + 0.01);
            gain.gain.exponentialRampToValueAtTime(0.001, start + 1.6);
            osc.connect(gain);
            gain.connect(output);
            osc.start(start);
            osc.stop(start + 1.7);
        });
    }

    // a quiet warm chord under the melody
    function pad(rootMidi, third, start, length, output) {
        [0, third, 7].forEach(function(interval) {
            const osc = audio.createOscillator();
            const gain = audio.createGain();
            osc.type = "sine";
            osc.frequency.value = midiToFrequency(rootMidi + interval);
            gain.gain.setValueAtTime(0, start);
            gain.gain.linearRampToValueAtTime(0.06, start + 1.2);
            gain.gain.setValueAtTime(0.06, start + length - 1.5);
            gain.gain.linearRampToValueAtTime(0, start + length);
            osc.connect(gain);
            gain.connect(output);
            osc.start(start);
            osc.stop(start + length + 0.1);
        });
    }

    function stop() {
        clearTimeout(stopTimer);
        if (audio) {
            audio.close();
            audio = null;
        }
        if (whenDone) {
            const done = whenDone;
            whenDone = null;
            done();
        }
    }

    function play(palette, moodName, onDone) {
        stop();
        if (!palette || palette.length === 0) return;
        whenDone = onDone || null;
        const style = styleFor(moodName);
        audio = new (window.AudioContext || window.webkitAudioContext)();

        // gentle echo, a little muffled, like a quiet room at night
        const master = audio.createGain();
        master.gain.value = 0.35;
        const echo = audio.createDelay();
        echo.delayTime.value = 0.28;
        const feedback = audio.createGain();
        feedback.gain.value = 0.25;
        const soften = audio.createBiquadFilter();
        soften.type = "lowpass";
        soften.frequency.value = 2200;
        master.connect(audio.destination);
        master.connect(echo);
        echo.connect(soften);
        soften.connect(feedback);
        feedback.connect(echo);
        soften.connect(audio.destination);

        // melody: the colors forward, then back, then home to the root note
        const notes = palette.map(function(hex) { return colorToMidi(hex, style); });
        const melody = notes.concat(notes.slice(0, -1).reverse(), [style.base]);
        const now = audio.currentTime + 0.1;
        const total = melody.length * style.step + 1.5;

        pad(style.base - 12, style.third, now, total, master);
        melody.forEach(function(midi, i) {
            bell(midiToFrequency(midi), now + i * style.step, master);
        });

        stopTimer = setTimeout(stop, (total + 1) * 1000);
    }

    window.BookMusic = {
        play: play,
        stop: stop,
        isPlaying: function() { return audio !== null; }
    };
})();
