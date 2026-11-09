// SmartGram Voice Recognition Service (Web Speech API)
let recognition = null;
let isRecording = false;

function initVoiceRecognition(descriptionFieldId, statusFieldId, langSelectId) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  
  if (!SpeechRecognition) {
    console.warn("Speech Recognition API not supported in this browser.");
    const statusElem = document.getElementById(statusFieldId);
    if (statusElem) {
      statusElem.innerHTML = `<span style="color: #64748b;">(Voice input not supported in your browser. Type description manually.)</span>`;
    }
    const btn = document.getElementById("voiceRecordBtn");
    if (btn) btn.style.display = "none";
    return false;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;

  const descField = document.getElementById(descriptionFieldId);
  const statusElem = document.getElementById(statusFieldId);
  const langSelect = document.getElementById(langSelectId);

  recognition.onstart = function() {
    isRecording = true;
    updateVoiceUI(true);
    if (statusElem) {
      statusElem.innerHTML = `<span style="color: #ef4444; font-weight: 600;">🎙️ Listening... Speak your village grievance clearly. Click Stop when finished.</span>`;
    }
  };

  recognition.onresult = function(event) {
    let interimTranscript = '';
    let finalTranscript = '';

    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        finalTranscript += event.results[i][0].transcript + ' ';
      } else {
        interimTranscript += event.results[i][0].transcript;
      }
    }

    if (finalTranscript && descField) {
      // Append to existing text or insert
      const currentVal = descField.value.trim();
      descField.value = currentVal ? currentVal + ' ' + finalTranscript.trim() : finalTranscript.trim();
      
      // Mark voice_recorded flag
      const voiceFlag = document.getElementById("voice_recorded");
      if (voiceFlag) voiceFlag.value = "true";

      // Trigger AI Classification preview
      triggerAIClassificationPreview();
    }
  };

  recognition.onerror = function(event) {
    console.error("Speech recognition error:", event.error);
    if (statusElem) {
      statusElem.innerHTML = `<span style="color: #b91c1c;">Voice error: ${event.error}. Please try again or type manually.</span>`;
    }
    stopVoiceRecognition();
  };

  recognition.onend = function() {
    isRecording = false;
    updateVoiceUI(false);
    if (statusElem) {
      statusElem.innerHTML = `<span style="color: #059669; font-weight: 600;">✓ Voice transcribed into editable text. Feel free to edit or add details.</span>`;
    }
    triggerAIClassificationPreview();
  };

  return true;
}

function toggleVoiceRecording() {
  if (!recognition) {
    const initialized = initVoiceRecognition("description", "voiceStatus", "voiceLang");
    if (!initialized) return;
  }

  const langSelect = document.getElementById("voiceLang");
  if (langSelect && recognition) {
    recognition.lang = langSelect.value || 'en-IN';
  }

  if (isRecording) {
    recognition.stop();
  } else {
    try {
      recognition.start();
    } catch (e) {
      console.warn("Recognition start failed or already active:", e);
    }
  }
}

function updateVoiceUI(recording) {
  const btn = document.getElementById("voiceRecordBtn");
  const icon = document.getElementById("voiceIcon");
  const text = document.getElementById("voiceBtnText");
  if (!btn) return;

  if (recording) {
    btn.classList.add("recording");
    btn.style.backgroundColor = "#b91c1c";
    if (text) text.innerText = "Stop Speaking";
  } else {
    btn.classList.remove("recording");
    btn.style.backgroundColor = "#ef4444";
    if (text) text.innerText = "Speak Complaint (Voice Input)";
  }
}

// AI Classification Preview Helper
function triggerAIClassificationPreview() {
  const titleField = document.getElementById("title");
  const descField = document.getElementById("description");
  const aiBox = document.getElementById("aiClassificationPreview");

  const title = titleField ? titleField.value.trim() : "";
  const desc = descField ? descField.value.trim() : "";

  if (!title && !desc) return;
  if (aiBox) aiBox.style.display = "block";

  fetch("/api/classify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title, description: desc })
  })
  .then(res => res.json())
  .then(data => {
    if (aiBox) {
      document.getElementById("aiCategoryText").innerText = data.category + " (" + data.subcategory + ")";
      const urgElem = document.getElementById("aiUrgencyText");
      urgElem.innerText = data.urgency + " (Score: " + data.priority_score + "/100)";
      urgElem.className = "badge badge-" + data.urgency.toLowerCase();
      
      document.getElementById("aiSummaryText").innerText = data.summary;

      // Auto-select Category dropdown if user hasn't explicitly chosen one
      const catSelect = document.getElementById("category");
      if (catSelect && (!catSelect.value || catSelect.value === "")) {
        catSelect.value = data.category;
        if (typeof updateSubcategories === 'function') updateSubcategories();
      }
    }
  })
  .catch(err => console.log("AI Preview error:", err));
}
