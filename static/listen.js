// Free audiobooks from LibriVox (read by volunteers), shown on the book page.
// The page needs:  <div id="listen-slot" data-work="OL...W"></div>
(function() {
    const slot = document.getElementById("listen-slot");
    if (!slot) return;

    const style = document.createElement("style");
    style.textContent = `
        #listen-slot:empty { display: none; }
        .audiobook { margin: 18px 0 6px; padding: 18px 20px; border-radius: 20px; border: 1px solid var(--line); background: var(--glass); animation: rise 0.7s var(--ease) both; }
        .audiobook .head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
        .audiobook strong { color: var(--moon); font-weight: 800; }
        .audiobook .head span { font-size: 13px; }
        .audiobook select { width: 100%; padding: 10px 14px; margin-bottom: 12px; border-radius: 14px; border: 1px solid var(--line); background: rgba(13, 16, 48, 0.8); color: var(--moon); font: inherit; font-size: 15px; }
        .audiobook audio { width: 100%; height: 40px; color-scheme: dark; }
        .audiobook .credit { margin: 10px 0 0; font-size: 12px; }
    `;
    document.head.appendChild(style);

    const workId = slot.dataset.work;

    fetch("/api/listen/" + workId)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.found) return;

            const box = document.createElement("div");
            box.className = "audiobook";

            const head = document.createElement("div");
            head.className = "head";
            const title = document.createElement("strong");
            title.textContent = "🎧 Listen to the audiobook";
            const total = document.createElement("span");
            const minutes = data.chapters.reduce(function(sum, c) { return sum + c.minutes; }, 0);
            total.textContent = data.chapters.length + " parts · about " + (minutes >= 90 ? Math.round(minutes / 60) + " hours" : minutes + " min");
            head.append(title, total);

            const select = document.createElement("select");
            data.chapters.forEach(function(chapter, i) {
                const option = document.createElement("option");
                option.value = i;
                option.textContent = (i + 1) + ". " + chapter.title + " (" + chapter.minutes + " min)";
                select.appendChild(option);
            });

            const audio = document.createElement("audio");
            audio.controls = true;
            audio.preload = "none";

            // remember where the listener stopped
            const key = "listen-" + workId;
            let saved = { part: 0, time: 0 };
            try { saved = JSON.parse(localStorage.getItem(key)) || saved; } catch (e) {}
            if (saved.part >= data.chapters.length) saved = { part: 0, time: 0 };

            function load(i, time) {
                select.value = i;
                audio.src = data.chapters[i].url;
                if (time) audio.addEventListener("loadedmetadata", function seek() {
                    audio.currentTime = time;
                    audio.removeEventListener("loadedmetadata", seek);
                });
            }
            load(saved.part, saved.time);

            select.addEventListener("change", function() {
                load(Number(select.value), 0);
                audio.play().catch(function() {});
            });
            audio.addEventListener("timeupdate", function() {
                if (Math.floor(audio.currentTime) % 5 !== 0) return;
                try { localStorage.setItem(key, JSON.stringify({ part: Number(select.value), time: audio.currentTime })); } catch (e) {}
            });
            audio.addEventListener("play", function() {
                if (window.BookMusic && BookMusic.isPlaying()) BookMusic.stop();
            });
            audio.addEventListener("ended", function() {
                const next = Number(select.value) + 1;
                if (next < data.chapters.length) {
                    load(next, 0);
                    audio.play().catch(function() {});
                }
            });

            const credit = document.createElement("p");
            credit.className = "credit";
            const link = document.createElement("a");
            link.href = /^https?:\/\//.test(data.page || "") ? data.page : "https://librivox.org";
            link.target = "_blank";
            link.rel = "noopener";
            link.textContent = "LibriVox";
            credit.append("Read by volunteers of ", link, " · public domain");

            box.append(head, select, audio, credit);
            slot.appendChild(box);
        })
        .catch(function() {});
})();
