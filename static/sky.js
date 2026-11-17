// Sound generation and parts of this file written with help from Claude.
// ☾ The living sky of the reader.
// The sky reads the page together with you: it looks at the words of the paragraphs
// on your screen and turns them into weather — rain, snow, stars, fire, the sea...
// Everything is drawn with code (canvas) and every sound is made with code (Web Audio).
(function() {
    // ---------- 1. which words make which sky ----------
    const SCENES = {
        rain:    { icon: "☂", name: "rain",          words: ["rain", "rains", "raining", "rained", "rainy", "drizzle", "shower", "showers", "umbrella", "wet", "puddle", "puddles", "drops"] },
        storm:   { icon: "⚡", name: "a storm",       words: ["storm", "storms", "stormy", "thunder", "lightning", "tempest", "gale", "hurricane"] },
        snow:    { icon: "❄", name: "snow",          words: ["snow", "snowy", "snowing", "snowflakes", "frost", "frosty", "ice", "icy", "frozen", "winter", "sleigh", "christmas"] },
        night:   { icon: "✦", name: "a starry night", words: ["night", "nights", "midnight", "moon", "moonlight", "moonlit", "star", "stars", "starlight", "evening", "darkness", "dusk"] },
        fire:    { icon: "🕯", name: "firelight",     words: ["fire", "fires", "fireplace", "fireside", "hearth", "flame", "flames", "candle", "candles", "candlelight", "lamp", "embers", "burning", "blaze"] },
        sea:     { icon: "🌊", name: "the sea",       words: ["sea", "seas", "ocean", "waves", "wave", "shore", "ship", "ships", "sail", "sailed", "sailing", "harbour", "harbor", "beach", "tide", "boat", "island"] },
        sun:     { icon: "☀", name: "sunlight",      words: ["sun", "sunny", "sunshine", "sunlight", "summer", "golden", "noon", "sunset", "sunrise", "dawn", "bright"] },
        wind:    { icon: "🍂", name: "autumn wind",   words: ["wind", "winds", "windy", "breeze", "leaves", "autumn", "blew", "blowing", "gust", "gusts", "october"] },
        flowers: { icon: "🌸", name: "a garden",      words: ["flower", "flowers", "garden", "gardens", "rose", "roses", "blossom", "blossoms", "spring", "bloom", "blooming", "petals", "lilac", "violets", "meadow"] }
    };
    const QUIET = { icon: "☾", name: "a quiet night" };

    const wordToScene = {};
    Object.keys(SCENES).forEach(function(key) {
        SCENES[key].words.forEach(function(word) { wordToScene[word] = key; });
    });

    function scoreText(text) {
        const score = {};
        const words = text.toLowerCase().match(/[a-z]+/g) || [];
        words.forEach(function(word) {
            const scene = wordToScene[word];
            if (scene) score[scene] = (score[scene] || 0) + 1;
        });
        return score;
    }

    // ---------- 2. the canvas ----------
    const canvas = document.createElement("canvas");
    canvas.className = "living-sky";
    canvas.setAttribute("aria-hidden", "true");
    Object.assign(canvas.style, {
        position: "fixed", inset: "0", width: "100%", height: "100%",
        zIndex: "-1", pointerEvents: "none"
    });
    document.body.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    let W = 0, H = 0;

    function resize() {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        W = window.innerWidth;
        H = window.innerHeight;
        canvas.width = W * dpr;
        canvas.height = H * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener("resize", resize);

    function rand(a, b) { return a + Math.random() * (b - a); }
    function many(n, make) { const list = []; for (let i = 0; i < n; i++) list.push(make(true)); return list; }

    // ---------- 3. how every sky looks ----------
    const painters = {
        rain: (function() {
            function drop(anywhere) { return { x: rand(-100, W + 100), y: anywhere ? rand(-H, H) : rand(-200, -20), len: rand(12, 26), speed: rand(9, 15) }; }
            let drops = null;
            return function(a) {
                drops = drops || many(170, drop);
                ctx.strokeStyle = "rgba(190, 205, 255, " + (0.35 * a) + ")";
                ctx.lineWidth = 1.2;
                ctx.beginPath();
                drops.forEach(function(d, i) {
                    ctx.moveTo(d.x, d.y);
                    ctx.lineTo(d.x - d.len * 0.25, d.y + d.len);
                    d.y += d.speed; d.x -= d.speed * 0.25;
                    if (d.y > H) drops[i] = drop(false);
                });
                ctx.stroke();
            };
        })(),

        storm: (function() {
            let flash = 0;
            return function(a) {
                painters.rain(a * 1.3);
                painters.rain(a * 0.8);
                if (Math.random() < 0.004) flash = 1;
                if (flash > 0.01) {
                    ctx.fillStyle = "rgba(225, 230, 255, " + (0.28 * flash * a) + ")";
                    ctx.fillRect(0, 0, W, H);
                    flash *= 0.9;
                }
            };
        })(),

        snow: (function() {
            function flake(anywhere) { return { x: rand(0, W), y: anywhere ? rand(0, H) : -10, r: rand(1, 3.4), speed: rand(0.4, 1.3), sway: rand(0, 6.28) }; }
            let flakes = null;
            return function(a, t) {
                flakes = flakes || many(150, flake);
                ctx.fillStyle = "rgba(244, 241, 255, " + (0.8 * a) + ")";
                ctx.beginPath();
                flakes.forEach(function(f, i) {
                    f.y += f.speed;
                    f.x += Math.sin(t / 1200 + f.sway) * 0.5;
                    ctx.moveTo(f.x + f.r, f.y);
                    ctx.arc(f.x, f.y, f.r, 0, 6.28);
                    if (f.y > H + 5) flakes[i] = flake(false);
                });
                ctx.fill();
            };
        })(),

        night: (function() {
            let stars = null;
            let shooting = null;
            return function(a, t) {
                stars = stars || many(140, function() { return { x: rand(0, W), y: rand(0, H), r: rand(0.6, 1.8), p: rand(0, 6.28) }; });
                stars.forEach(function(s) {
                    const glow = 0.35 + 0.65 * Math.abs(Math.sin(t / 900 + s.p));
                    ctx.fillStyle = "rgba(255, 248, 214, " + (glow * a) + ")";
                    ctx.beginPath();
                    ctx.arc(s.x, s.y, s.r, 0, 6.28);
                    ctx.fill();
                });
                if (!shooting && Math.random() < 0.006) shooting = { x: rand(W * 0.2, W), y: rand(0, H * 0.4), life: 1 };
                if (shooting) {
                    const g = ctx.createLinearGradient(shooting.x, shooting.y, shooting.x + 120, shooting.y - 50);
                    g.addColorStop(0, "rgba(255, 255, 255, " + (shooting.life * a) + ")");
                    g.addColorStop(1, "rgba(255, 255, 255, 0)");
                    ctx.strokeStyle = g;
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    ctx.moveTo(shooting.x, shooting.y);
                    ctx.lineTo(shooting.x + 120, shooting.y - 50);
                    ctx.stroke();
                    shooting.x -= 9; shooting.y += 3.75; shooting.life -= 0.02;
                    if (shooting.life <= 0) shooting = null;
                }
            };
        })(),

        fire: (function() {
            function ember(anywhere) { return { x: rand(0, W), y: anywhere ? rand(H * 0.3, H) : H + 10, r: rand(1, 3), speed: rand(0.6, 1.8), sway: rand(0, 6.28), hue: rand(18, 45) }; }
            let embers = null;
            return function(a, t) {
                embers = embers || many(90, ember);
                const glow = ctx.createRadialGradient(W / 2, H + 80, 10, W / 2, H + 80, H * 0.9);
                glow.addColorStop(0, "rgba(255, 140, 60, " + (0.28 * a * (0.85 + 0.15 * Math.sin(t / 180))) + ")");
                glow.addColorStop(1, "rgba(255, 140, 60, 0)");
                ctx.fillStyle = glow;
                ctx.fillRect(0, 0, W, H);
                embers.forEach(function(e, i) {
                    e.y -= e.speed;
                    e.x += Math.sin(t / 500 + e.sway) * 0.6;
                    const life = Math.max(0, e.y / H);
                    ctx.fillStyle = "hsla(" + e.hue + ", 100%, 65%, " + (life * 0.9 * a) + ")";
                    ctx.beginPath();
                    ctx.arc(e.x, e.y, e.r, 0, 6.28);
                    ctx.fill();
                    if (e.y < H * 0.15) embers[i] = ember(false);
                });
            };
        })(),

        sea: function(a, t) {
            for (let layer = 0; layer < 4; layer++) {
                const base = H * (0.7 + layer * 0.08);
                ctx.fillStyle = "rgba(" + (90 + layer * 20) + ", " + (130 + layer * 15) + ", 255, " + (0.07 + layer * 0.025) * a + ")";
                ctx.beginPath();
                ctx.moveTo(0, H);
                for (let x = 0; x <= W + 20; x += 20) {
                    const y = base + Math.sin(x / (160 - layer * 20) + t / (1400 - layer * 200) + layer) * (14 - layer * 2);
                    ctx.lineTo(x, y);
                }
                ctx.lineTo(W, H);
                ctx.fill();
            }
            // little glints of moonlight on the water
            for (let i = 0; i < 26; i++) {
                const x = (i * 97.3 + t / 40) % W;
                const y = H * 0.74 + (i % 5) * H * 0.045;
                const glow = Math.max(0, Math.sin(t / 600 + i)) * a;
                ctx.fillStyle = "rgba(244, 241, 255, " + glow * 0.6 + ")";
                ctx.fillRect(x, y, 14, 1.5);
            }
        },

        sun: (function() {
            let motes = null;
            return function(a, t) {
                motes = motes || many(80, function() { return { x: rand(0, W), y: rand(0, H), r: rand(1, 2.6), sx: rand(-0.2, 0.2), sy: rand(-0.3, -0.05), p: rand(0, 6.28) }; });
                const glow = ctx.createRadialGradient(W * 0.88, -40, 10, W * 0.88, -40, H);
                glow.addColorStop(0, "rgba(255, 214, 140, " + 0.32 * a + ")");
                glow.addColorStop(1, "rgba(255, 214, 140, 0)");
                ctx.fillStyle = glow;
                ctx.fillRect(0, 0, W, H);
                motes.forEach(function(m) {
                    m.x += m.sx; m.y += m.sy;
                    if (m.y < -5) { m.y = H + 5; m.x = rand(0, W); }
                    ctx.fillStyle = "rgba(255, 230, 170, " + (0.5 + 0.5 * Math.sin(t / 700 + m.p)) * 0.7 * a + ")";
                    ctx.beginPath();
                    ctx.arc(m.x, m.y, m.r, 0, 6.28);
                    ctx.fill();
                });
            };
        })(),

        wind: (function() {
            const colors = ["#e0893b", "#c8553d", "#f2b84b", "#a8642a"];
            function leaf(anywhere) { return { x: anywhere ? rand(-50, W) : -30, y: rand(-50, H), size: rand(5, 10), speed: rand(1.5, 3.5), turn: rand(0, 6.28), spin: rand(-0.05, 0.05), color: colors[Math.floor(rand(0, colors.length))] }; }
            let leaves = null;
            return function(a, t) {
                leaves = leaves || many(46, leaf);
                ctx.globalAlpha = 0.75 * a;
                leaves.forEach(function(l, i) {
                    l.x += l.speed;
                    l.y += Math.sin(t / 700 + l.turn) * 1.2 + 0.4;
                    l.turn += l.spin;
                    ctx.save();
                    ctx.translate(l.x, l.y);
                    ctx.rotate(l.turn);
                    ctx.fillStyle = l.color;
                    ctx.beginPath();
                    ctx.ellipse(0, 0, l.size, l.size * 0.45, 0, 0, 6.28);
                    ctx.fill();
                    ctx.restore();
                    if (l.x > W + 30 || l.y > H + 30) leaves[i] = leaf(false);
                });
                ctx.globalAlpha = 1;
            };
        })(),

        flowers: (function() {
            const colors = ["#ffc4dd", "#ffd9e8", "#f7a8c8", "#fff0f6"];
            function petal(anywhere) { return { x: rand(0, W), y: anywhere ? rand(0, H) : -15, size: rand(4, 8), speed: rand(0.6, 1.4), turn: rand(0, 6.28), sway: rand(0, 6.28), color: colors[Math.floor(rand(0, colors.length))] }; }
            let petals = null;
            return function(a, t) {
                petals = petals || many(60, petal);
                ctx.globalAlpha = 0.8 * a;
                petals.forEach(function(p, i) {
                    p.y += p.speed;
                    p.x += Math.sin(t / 900 + p.sway) * 0.8;
                    p.turn += 0.02;
                    ctx.save();
                    ctx.translate(p.x, p.y);
                    ctx.rotate(p.turn);
                    ctx.fillStyle = p.color;
                    ctx.beginPath();
                    ctx.ellipse(0, 0, p.size, p.size * 0.6, 0, 0, 6.28);
                    ctx.fill();
                    ctx.restore();
                    if (p.y > H + 15) petals[i] = petal(false);
                });
                ctx.globalAlpha = 1;
            };
        })()
    };

    // ---------- 4. how every sky sounds (all made with code) ----------
    let audio = null;
    const voices = {};
    let soundOn = false;

    function noiseBuffer(kind) {
        const length = audio.sampleRate * 3;
        const buffer = audio.createBuffer(1, length, audio.sampleRate);
        const data = buffer.getChannelData(0);
        let last = 0;
        for (let i = 0; i < length; i++) {
            const white = Math.random() * 2 - 1;
            if (kind === "brown") {
                last = (last + 0.02 * white) / 1.02;
                data[i] = last * 3.5;
            } else {
                data[i] = white;
            }
        }
        return buffer;
    }

    // a looping noise, shaped by a filter: rain, wind, waves and fire are all made like this
    function noiseVoice(kind, type, frequency, q, waveSpeed) {
        const source = audio.createBufferSource();
        source.buffer = noiseBuffer(kind);
        source.loop = true;
        const filter = audio.createBiquadFilter();
        filter.type = type;
        filter.frequency.value = frequency;
        filter.Q.value = q;
        const gain = audio.createGain();
        gain.gain.value = 0;
        source.connect(filter);
        filter.connect(gain);
        if (waveSpeed) {
            // the sound slowly breathes in and out, like waves or gusts of wind
            const lfo = audio.createOscillator();
            const depth = audio.createGain();
            lfo.frequency.value = waveSpeed;
            depth.gain.value = 0.5;
            const breathing = audio.createGain();
            breathing.gain.value = 0.5;
            lfo.connect(depth);
            depth.connect(breathing.gain);
            filter.disconnect();
            filter.connect(breathing);
            breathing.connect(gain);
            lfo.start();
        }
        gain.connect(audio.destination);
        source.start();
        return gain;
    }

    const SOUNDS = {
        rain:    function() { return noiseVoice("white", "bandpass", 2500, 0.5, 0); },
        storm:   function() { return noiseVoice("brown", "lowpass", 900, 0.7, 0.08); },
        snow:    function() { return noiseVoice("brown", "lowpass", 420, 0.5, 0.06); },
        night:   function() { return noiseVoice("brown", "lowpass", 300, 0.4, 0.05); },
        fire:    function() { return noiseVoice("brown", "lowpass", 600, 0.8, 0.9); },
        sea:     function() { return noiseVoice("brown", "lowpass", 700, 0.6, 0.11); },
        sun:     function() { return noiseVoice("white", "bandpass", 5200, 3, 0.2); },
        wind:    function() { return noiseVoice("white", "bandpass", 600, 1.4, 0.15); },
        flowers: function() { return noiseVoice("white", "bandpass", 4000, 2, 0.25); }
    };
    const LOUDNESS = { rain: 0.12, storm: 0.3, snow: 0.2, night: 0.12, fire: 0.3, sea: 0.32, sun: 0.02, wind: 0.08, flowers: 0.02 };

    // little extra sounds: crackles of the fire, birds in the garden and the sun, thunder in the storm
    function crackle() {
        const now = audio.currentTime;
        const source = audio.createBufferSource();
        source.buffer = noiseBuffer("white");
        const gain = audio.createGain();
        const filter = audio.createBiquadFilter();
        filter.type = "highpass";
        filter.frequency.value = 1800;
        gain.gain.setValueAtTime(rand(0.05, 0.16), now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + rand(0.02, 0.07));
        source.connect(filter); filter.connect(gain); gain.connect(audio.destination);
        source.start(now, rand(0, 2), 0.1);
    }
    function chirp() {
        const now = audio.currentTime;
        const notes = Math.floor(rand(2, 4));
        for (let i = 0; i < notes; i++) {
            const osc = audio.createOscillator();
            const gain = audio.createGain();
            const start = now + i * 0.12;
            const f = rand(2600, 3600);
            osc.frequency.setValueAtTime(f, start);
            osc.frequency.exponentialRampToValueAtTime(f * 1.3, start + 0.08);
            gain.gain.setValueAtTime(0, start);
            gain.gain.linearRampToValueAtTime(0.025, start + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, start + 0.1);
            osc.connect(gain); gain.connect(audio.destination);
            osc.start(start); osc.stop(start + 0.12);
        }
    }
    function thunder() {
        const now = audio.currentTime;
        const source = audio.createBufferSource();
        source.buffer = noiseBuffer("brown");
        const filter = audio.createBiquadFilter();
        filter.type = "lowpass";
        filter.frequency.value = 160;
        const gain = audio.createGain();
        gain.gain.setValueAtTime(0, now);
        gain.gain.linearRampToValueAtTime(0.9, now + 0.3);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 3);
        source.connect(filter); filter.connect(gain); gain.connect(audio.destination);
        source.start(now); source.stop(now + 3);
    }

    // ---------- 5. which sky is on the screen right now ----------
    const intensity = {};
    Object.keys(painters).forEach(function(k) { intensity[k] = 0; });
    let scene = null;
    const listeners = [];

    function setScene(next) {
        if (next === scene) return;
        scene = next;
        listeners.forEach(function(fn) { fn(scene ? SCENES[scene] : QUIET, scene); });
        updateSound();
    }

    function updateSound() {
        if (!audio) return;
        const now = audio.currentTime;
        Object.keys(SOUNDS).forEach(function(key) {
            const target = soundOn && key === scene ? LOUDNESS[key] : 0;
            if (target > 0 && !voices[key]) voices[key] = SOUNDS[key]();
            if (voices[key]) {
                voices[key].gain.cancelScheduledValues(now);
                voices[key].gain.setTargetAtTime(target, now, 0.8);
            }
        });
    }

    let paragraphs = [];
    function watch(elements) {
        paragraphs = Array.prototype.map.call(elements, function(el) {
            return { el: el, score: scoreText(el.textContent) };
        });
        pickScene();
    }

    // add up the words of everything you can see; the strongest weather wins
    function pickScene() {
        const total = {};
        const middle = H / 2;
        paragraphs.forEach(function(p) {
            const box = p.el.getBoundingClientRect();
            if (box.bottom < 0 || box.top > H) return;
            // paragraphs near the middle of the screen count a little more
            const center = (box.top + box.bottom) / 2;
            const weight = 1.4 - Math.min(1, Math.abs(center - middle) / H);
            Object.keys(p.score).forEach(function(k) { total[k] = (total[k] || 0) + p.score[k] * weight; });
        });
        let best = null;
        let bestScore = 1.5;
        Object.keys(total).forEach(function(k) {
            if (total[k] > bestScore) { best = k; bestScore = total[k]; }
        });
        setScene(best);
    }
    let scrollTimer = null;
    window.addEventListener("scroll", function() {
        clearTimeout(scrollTimer);
        scrollTimer = setTimeout(pickScene, 150);
    }, { passive: true });

    // ---------- 6. drawing, 60 times a second ----------
    let lastTime = 0;
    function frame(t) {
        ctx.clearRect(0, 0, W, H);
        Object.keys(painters).forEach(function(k) {
            const target = k === scene ? 1 : 0;
            intensity[k] += (target - intensity[k]) * 0.03;
            if (intensity[k] > 0.01) painters[k](intensity[k], t);
        });
        if (audio && soundOn && scene && t - lastTime > 120) {
            lastTime = t;
            if (scene === "fire" && Math.random() < 0.35) crackle();
            if ((scene === "flowers" || scene === "sun") && Math.random() < 0.025) chirp();
            if (scene === "storm" && Math.random() < 0.012) thunder();
        }
        requestAnimationFrame(frame);
    }
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) requestAnimationFrame(frame);

    window.LivingSky = {
        watch: watch,
        onChange: function(fn) { listeners.push(fn); fn(scene ? SCENES[scene] : QUIET, scene); },
        toggleSound: function() {
            soundOn = !soundOn;
            if (soundOn && !audio) audio = new (window.AudioContext || window.webkitAudioContext)();
            if (audio && audio.state === "suspended") audio.resume();
            updateSound();
            return soundOn;
        }
    };
})();
