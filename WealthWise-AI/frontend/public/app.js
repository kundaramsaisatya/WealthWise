const chatForm = document.getElementById("chat-form");
const chatBox = document.getElementById("chat-box");
const questionInput = document.getElementById("question");

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const question = questionInput.value.trim();
    if (!question) return;

    chatBox.innerHTML += `
        <div class="message"><strong>You:</strong> ${escapeHTML(question)}</div>
    `;

    questionInput.value = "";

    const loading = document.createElement("div");
    loading.className = "message";
    loading.textContent = "WealthWise AI is thinking...";
    chatBox.appendChild(loading);

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question })
        });

        const data = await response.json();
        const answer = data.answer || data.error || "No answer received.";

loading.textContent = (
    data.answer || data.error || "No answer received."
)
.replace(/\\\*/g, "")
.replace(/\*\*/g, "");

        if (data.sources?.length) {
            const sources = document.createElement("div");
            sources.className = "message";
            sources.textContent = "Retrieved sources: " +
                data.sources.map(s =>
                    `${s.source || s.filename || s.file || "Uploaded document"}, page ${s.page ?? "unknown"}`
                ).join("; ");
            chatBox.appendChild(sources);
        }
    } catch (error) {
        loading.textContent = "Unable to connect to the AI service.";
    }

    chatBox.scrollTop = chatBox.scrollHeight;
});

function escapeHTML(value) {
    return value.replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    })[character]);
}

const explainButton = document.getElementById("explain-risk-btn");
const explanationResult = document.getElementById("risk-explanation-result");

if (explainButton) {
    explainButton.addEventListener("click", async () => {
        explainButton.disabled = true;
        explainButton.textContent = "Generating explanation...";

        try {
            const response = await fetch("/risk/explanation", {
                method: "POST"
            });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error);
            }

explanationResult.textContent = data.explanation
    .replace(/\*\*/g, "")
    .replace(/\*/g, "")
    .replace(/^#{1,6}\s/gm, "");
        } catch (error) {
            explanationResult.textContent = error.message;
        }

        explainButton.disabled = false;
        explainButton.textContent = "Explain Portfolio Risk";
    });
}

const historyButton = document.getElementById("load-history-btn");
const historyContainer = document.getElementById("chat-history");

if (historyButton) {
    historyButton.addEventListener("click", async () => {
        historyButton.disabled = true;
        historyButton.textContent = "Loading...";

        try {
            const response = await fetch("/chat/history");
            const data = await response.json();

            historyContainer.replaceChildren();

            data.messages.forEach(message => {
                const item = document.createElement("div");
                item.className = "message";

                const heading = document.createElement("strong");
                heading.textContent =
                    message.role === "user" ? "You: " : "WealthWise AI: ";

                const content = document.createElement("span");
                content.textContent = message.content;

                item.append(heading, content);
                historyContainer.appendChild(item);
            });

            if (!data.messages.length) {
                historyContainer.textContent = "No previous conversations.";
            }

        } catch (error) {
            historyContainer.textContent = "Unable to load chat history.";
        }

        historyButton.disabled = false;
        historyButton.textContent = "View Previous Conversations";
    });
}

document.addEventListener("DOMContentLoaded", () => {
    const syncBtn = document.getElementById("syncPortfolioBtn");
    const syncStatus = document.getElementById("syncStatus");

    if (!syncBtn) return;

    syncBtn.addEventListener("click", async () => {
        syncBtn.disabled = true;
        syncBtn.textContent = "Syncing...";

        try {
            const response = await fetch("/portfolio/sync", {
                method: "POST",
                credentials: "same-origin"
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || "Portfolio sync failed");
            }

            syncStatus.textContent = "Portfolio synced successfully!";

            location.reload();

        } catch (error) {
            console.error("Portfolio sync error:", error);

            syncStatus.textContent = error.message;
            syncBtn.disabled = false;
            syncBtn.textContent = "↻ Sync Portfolio";
        }
    });
});