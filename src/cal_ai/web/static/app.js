// Cal-AI Pipeline Page JavaScript
// SSE reader, stage tracker, terminal-style result rendering, drag-and-drop.
// Vanilla JS only — no framework dependencies.

(function () {
  "use strict";

  // -----------------------------------------------------------------------
  // DOM references
  // -----------------------------------------------------------------------
  var form = document.getElementById("pipeline-form");
  var submitBtn = document.getElementById("submit-btn");
  var concurrentMsg = document.getElementById("concurrent-msg");
  var fileInput = document.getElementById("file-input");
  var dropZone = document.getElementById("drop-zone");
  var fileNameEl = document.getElementById("file-name");
  var transcriptText = document.getElementById("transcript-text");
  var dryRunCheckbox = document.getElementById("dry-run-checkbox");
  var dryRunBanner = document.getElementById("dry-run-banner");
  var stageTracker = document.getElementById("stage-tracker");
  var terminalOutput = document.getElementById("terminal-output");
  var terminalContent = document.getElementById("terminal-content");
  var logViewer = document.getElementById("log-viewer");
  var logContent = document.getElementById("log-content");
  var errorDisplay = document.getElementById("error-display");
  var errorMessage = document.getElementById("error-message");
  var retryBtn = document.getElementById("retry-btn");

  // Tab elements
  var tabBtns = document.querySelectorAll(".input-tabs__btn");
  var tabUpload = document.getElementById("tab-upload");
  var tabPaste = document.getElementById("tab-paste");

  // Stage name -> DOM element ID mapping (SSE handler names -> HTML IDs).
  var STAGE_MAP = {
    "1_parse": "stage-1",
    "1b_memory": "stage-1b",
    "1c_calendar": "stage-1c",
    "2_extract": "stage-2",
    "3_sync": "stage-3",
    "4_memory_write": "stage-4",
  };

  // Ordered stage list for determining which stages to leave pending.
  var STAGE_ORDER = [
    "1_parse",
    "1b_memory",
    "1c_calendar",
    "2_extract",
    "3_sync",
    "4_memory_write",
  ];

  // Track the last form data for retry functionality.
  var lastFormData = null;

  // -----------------------------------------------------------------------
  // Tab switching
  // -----------------------------------------------------------------------
  tabBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var tab = btn.getAttribute("data-tab");
      tabBtns.forEach(function (b) {
        b.classList.remove("input-tabs__btn--active");
      });
      btn.classList.add("input-tabs__btn--active");
      tabUpload.classList.toggle("tab-panel--active", tab === "upload");
      tabPaste.classList.toggle("tab-panel--active", tab === "paste");
    });
  });

  // -----------------------------------------------------------------------
  // File reading helper (FileReader -> populate textarea with preview)
  // -----------------------------------------------------------------------
  function readFileIntoTextarea(file) {
    var reader = new FileReader();
    reader.onload = function (e) {
      transcriptText.value = e.target.result;
      fileNameEl.textContent = file.name;
      // Switch to the paste tab so user can see/edit the preview.
      tabBtns.forEach(function (b) {
        b.classList.remove("input-tabs__btn--active");
      });
      tabBtns[1].classList.add("input-tabs__btn--active");
      tabUpload.classList.remove("tab-panel--active");
      tabPaste.classList.add("tab-panel--active");
    };
    reader.readAsText(file);
  }

  // -----------------------------------------------------------------------
  // File picker
  // -----------------------------------------------------------------------
  fileInput.addEventListener("change", function () {
    if (fileInput.files && fileInput.files.length > 0) {
      readFileIntoTextarea(fileInput.files[0]);
    }
  });

  // -----------------------------------------------------------------------
  // Drag-and-drop
  // -----------------------------------------------------------------------
  dropZone.addEventListener("dragover", function (e) {
    e.preventDefault();
    dropZone.classList.add("drop-zone--active");
  });

  dropZone.addEventListener("dragleave", function () {
    dropZone.classList.remove("drop-zone--active");
  });

  dropZone.addEventListener("drop", function (e) {
    e.preventDefault();
    dropZone.classList.remove("drop-zone--active");
    if (e.dataTransfer && e.dataTransfer.files.length > 0) {
      readFileIntoTextarea(e.dataTransfer.files[0]);
    }
  });

  // -----------------------------------------------------------------------
  // Ctrl+Enter shortcut
  // -----------------------------------------------------------------------
  transcriptText.addEventListener("keydown", function (e) {
    if (e.ctrlKey && e.key === "Enter") {
      e.preventDefault();
      form.dispatchEvent(new Event("submit", { cancelable: true }));
    }
  });

  // -----------------------------------------------------------------------
  // Stage tracker helpers
  // -----------------------------------------------------------------------
  function resetStageTracker() {
    STAGE_ORDER.forEach(function (stageName) {
      var elId = STAGE_MAP[stageName];
      var el = document.getElementById(elId);
      if (el) {
        var indicator = el.querySelector(".stage__indicator");
        indicator.className = "stage__indicator stage--pending";
      }
    });
  }

  function updateStage(name, status) {
    var elId = STAGE_MAP[name];
    if (!elId) return;
    var el = document.getElementById(elId);
    if (!el) return;
    var indicator = el.querySelector(".stage__indicator");
    indicator.className = "stage__indicator stage--" + status;
  }

  // -----------------------------------------------------------------------
  // Timestamp formatting: ISO -> readable (e.g. "Wed Mar 4, 12:00 PM")
  // -----------------------------------------------------------------------
  function formatTimestamp(isoStr) {
    if (!isoStr) return "";
    try {
      var d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      var opts = {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      };
      return d.toLocaleString("en-US", opts);
    } catch (_e) {
      return isoStr;
    }
  }

  function formatTimeRange(start, end) {
    var s = formatTimestamp(start);
    if (!end) return s;
    // For end time, just show the time portion if same day.
    try {
      var ds = new Date(start);
      var de = new Date(end);
      if (
        ds.getFullYear() === de.getFullYear() &&
        ds.getMonth() === de.getMonth() &&
        ds.getDate() === de.getDate()
      ) {
        var timeOpts = { hour: "numeric", minute: "2-digit", hour12: true };
        return s + " \u2013 " + de.toLocaleString("en-US", timeOpts);
      }
    } catch (_e) {
      // Fall through to full format.
    }
    return s + " \u2013 " + formatTimestamp(end);
  }

  // -----------------------------------------------------------------------
  // Terminal-style result rendering
  // -----------------------------------------------------------------------
  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function renderResult(data) {
    var lines = [];

    // Dry-run banner.
    if (data.dry_run) {
      lines.push(
        "\u26a0\ufe0f DRY RUN \u2014 no calendar changes made",
      );
      lines.push("");
    }

    // Events section.
    var syncedEvents = data.events_synced || [];
    var failedEvents = data.events_failed || [];
    var totalEvents = syncedEvents.length + failedEvents.length;

    if (totalEvents === 0) {
      lines.push("No calendar events found in this conversation.");
    } else {
      // Render synced events.
      syncedEvents.forEach(function (s) {
        var ev = s.event;
        var actionUpper = (s.action_taken || ev.action || "create").toUpperCase();

        // Status icon based on sync result.
        var icon;
        if (!s.success) {
          icon = "\u274c";
        } else if (data.dry_run) {
          icon = "\u23f8\ufe0f";
        } else {
          icon = "\u2705";
        }

        lines.push(icon + " " + actionUpper + ": " + ev.title);

        // Show matched event info for UPDATE/DELETE.
        if (
          (actionUpper === "UPDATE" || actionUpper === "DELETE") &&
          s.matched_event_title
        ) {
          var matchInfo = "   (matched: " + s.matched_event_title;
          if (s.matched_event_time) {
            matchInfo += ", " + formatTimestamp(s.matched_event_time);
          }
          matchInfo += ")";
          lines.push(matchInfo);
        }

        // Readable timestamp.
        lines.push("   " + formatTimeRange(ev.start_time, ev.end_time));

        // Reasoning.
        if (ev.reasoning) {
          lines.push("   Reasoning: " + ev.reasoning);
        }

        // Assumptions.
        if (ev.assumptions && ev.assumptions.length > 0) {
          ev.assumptions.forEach(function (a) {
            lines.push("   Assumed: " + a);
          });
        }

        // Sync status line.
        if (!s.success) {
          lines.push(
            "   \u274c Failed: " + (s.error || "Unknown error"),
          );
        } else if (data.dry_run) {
          lines.push("   \u23f8\ufe0f Dry run (not synced)");
        } else {
          lines.push("   \u2705 Synced");
        }

        lines.push("");
      });

      // Render failed events.
      failedEvents.forEach(function (f) {
        var ev = f.event;
        var actionUpper = (ev.action || "create").toUpperCase();

        lines.push("\u274c FAILED: " + ev.title);
        lines.push("   " + formatTimeRange(ev.start_time, ev.end_time));

        if (ev.reasoning) {
          lines.push("   Reasoning: " + ev.reasoning);
        }

        if (ev.assumptions && ev.assumptions.length > 0) {
          ev.assumptions.forEach(function (a) {
            lines.push("   Assumed: " + a);
          });
        }

        lines.push("   \u274c Failed: " + f.error);
        lines.push("");
      });
    }

    // Memory actions section (always shown).
    lines.push("\u2500".repeat(40));
    var memActions = data.memory_actions || [];
    if (memActions.length === 0) {
      if (data.dry_run) {
        lines.push(
          "\ud83e\udde0 Memory write skipped (dry-run mode)",
        );
      } else {
        lines.push("\ud83e\udde0 No memory updates.");
      }
    } else {
      lines.push("\ud83e\udde0 MEMORY UPDATES:");
      memActions.forEach(function (m) {
        var actionUpper = (m.action || "NOOP").toUpperCase();
        var line =
          "  \ud83e\udde0 " +
          actionUpper +
          ": [" +
          m.category +
          "] " +
          m.key;
        if (m.new_value) {
          line += ' = "' + m.new_value + '"';
        }
        line += " (" + (m.confidence || "medium") + ")";
        lines.push(line);
        if (m.reasoning) {
          lines.push("     Reasoning: " + m.reasoning);
        }
      });
    }
    lines.push("");

    // Token/cost footer.
    lines.push("\u2500".repeat(40));
    var tu = data.token_usage;
    if (tu && tu.total_tokens > 0) {
      var costStr =
        tu.estimated_cost_usd !== null && tu.estimated_cost_usd !== undefined
          ? "$" + tu.estimated_cost_usd.toFixed(4)
          : "N/A";
      lines.push(
        "Tokens: " +
          tu.prompt_tokens.toLocaleString() +
          " in / " +
          tu.output_tokens.toLocaleString() +
          " out \u2014 Est. cost: " +
          costStr,
      );
    } else {
      lines.push("Token usage unavailable");
    }

    // Summary line.
    var created = 0;
    var updated = 0;
    var deleted = 0;
    var failed = failedEvents.length;
    syncedEvents.forEach(function (s) {
      var action = (s.action_taken || s.event.action || "create").toLowerCase();
      if (action === "create" || action === "created") created++;
      else if (action === "update" || action === "updated") updated++;
      else if (action === "delete" || action === "deleted") deleted++;
    });

    var parts = [];
    if (created > 0) parts.push(created + " created");
    if (updated > 0) parts.push(updated + " updated");
    if (deleted > 0) parts.push(deleted + " deleted");
    if (failed > 0) parts.push(failed + " failed");
    if (parts.length === 0 && totalEvents === 0) {
      parts.push("0 events");
    }

    var warnings = data.warnings || [];
    if (warnings.length > 0) {
      parts.push(warnings.length + " warning" + (warnings.length > 1 ? "s" : ""));
    }

    var duration = data.duration_seconds
      ? data.duration_seconds.toFixed(1) + "s"
      : "N/A";

    lines.push(parts.join(", ") + " \u2014 " + duration);

    // Set terminal content.
    terminalContent.textContent = lines.join("\n");
    terminalOutput.hidden = false;
  }

  // -----------------------------------------------------------------------
  // SSE parser for POST-based streaming (fetch + ReadableStream)
  // -----------------------------------------------------------------------
  function parseSSEChunk(buffer) {
    // Split buffer on double newlines to find complete SSE events.
    var events = [];
    var parts = buffer.split("\n\n");
    // The last part may be incomplete (no trailing \n\n yet).
    var remainder = parts.pop();

    parts.forEach(function (block) {
      if (!block.trim()) return;
      var eventType = "message";
      var dataLines = [];

      block.split("\n").forEach(function (line) {
        if (line.startsWith("event: ")) {
          eventType = line.substring(7).trim();
        } else if (line.startsWith("data: ")) {
          dataLines.push(line.substring(6));
        } else if (line.startsWith("data:")) {
          dataLines.push(line.substring(5));
        }
      });

      if (dataLines.length > 0) {
        var dataStr = dataLines.join("\n");
        try {
          events.push({ type: eventType, data: JSON.parse(dataStr) });
        } catch (_e) {
          events.push({ type: eventType, data: { raw: dataStr } });
        }
      }
    });

    return { events: events, remainder: remainder || "" };
  }

  // -----------------------------------------------------------------------
  // UI state management
  // -----------------------------------------------------------------------
  function setRunning(running) {
    submitBtn.disabled = running;
    submitBtn.textContent = running ? "Running\u2026" : "Run Pipeline";
    concurrentMsg.hidden = true;
  }

  function resetResultsUI() {
    terminalOutput.hidden = true;
    terminalContent.textContent = "";
    logViewer.hidden = true;
    logContent.textContent = "";
    errorDisplay.hidden = true;
    dryRunBanner.hidden = true;
    stageTracker.hidden = true;
    resetStageTracker();
  }

  function showError(msg) {
    errorMessage.textContent = msg;
    errorDisplay.hidden = false;
  }

  // -----------------------------------------------------------------------
  // Pipeline submission
  // -----------------------------------------------------------------------
  function submitPipeline(formData) {
    lastFormData = formData;

    resetResultsUI();
    setRunning(true);

    // Show dry-run banner if checked.
    if (dryRunCheckbox.checked) {
      dryRunBanner.hidden = false;
    }

    // Show stage tracker.
    stageTracker.hidden = false;

    // Show log viewer (collapsed).
    logViewer.hidden = false;

    fetch("/api/pipeline/run", {
      method: "POST",
      body: formData,
    })
      .then(function (response) {
        if (response.status === 409) {
          setRunning(false);
          concurrentMsg.hidden = false;
          return;
        }

        if (response.status === 422) {
          return response.json().then(function (data) {
            setRunning(false);
            showError(data.detail || "Invalid input.");
          });
        }

        if (!response.ok) {
          setRunning(false);
          showError("Server error: HTTP " + response.status);
          return;
        }

        // Read the SSE stream.
        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";

        function read() {
          reader
            .read()
            .then(function (result) {
              if (result.done) {
                // Stream ended without a done event — treat as disconnect.
                setRunning(false);
                return;
              }

              buffer += decoder.decode(result.value, { stream: true });
              var parsed = parseSSEChunk(buffer);
              buffer = parsed.remainder;

              parsed.events.forEach(function (evt) {
                handleSSEEvent(evt);
              });

              read();
            })
            .catch(function (err) {
              setRunning(false);
              showError("Connection lost. Click to retry.");
            });
        }

        read();
      })
      .catch(function (err) {
        setRunning(false);
        showError("Connection lost. Click to retry.");
      });
  }

  function handleSSEEvent(evt) {
    switch (evt.type) {
      case "stage":
        updateStage(evt.data.name, evt.data.status);
        break;

      case "log":
        if (evt.data.message) {
          logContent.textContent +=
            "[" +
            (evt.data.level || "INFO") +
            "] " +
            evt.data.message +
            "\n";
          // Auto-scroll log viewer to bottom.
          logContent.scrollTop = logContent.scrollHeight;
        }
        break;

      case "result":
        renderResult(evt.data);
        break;

      case "error":
        var msg = evt.data.message || "An unknown error occurred.";
        // Mark any running stage as error.
        STAGE_ORDER.forEach(function (stageName) {
          var elId = STAGE_MAP[stageName];
          var el = document.getElementById(elId);
          if (el) {
            var indicator = el.querySelector(".stage__indicator");
            if (indicator.classList.contains("stage--running")) {
              indicator.className = "stage__indicator stage--error";
            }
          }
        });
        // Show error in terminal output area.
        terminalContent.textContent += "\n\u274c ERROR: " + msg + "\n";
        terminalOutput.hidden = false;
        break;

      case "done":
        setRunning(false);
        // Clear input after successful completion (results stay visible).
        transcriptText.value = "";
        fileInput.value = "";
        fileNameEl.textContent = "";
        break;
    }
  }

  // -----------------------------------------------------------------------
  // Form submit handler
  // -----------------------------------------------------------------------
  form.addEventListener("submit", function (e) {
    e.preventDefault();

    if (submitBtn.disabled) return;

    var formData = new FormData();

    // Determine input source: prefer textarea content (covers both paste
    // and file-preview-in-textarea cases), fall back to file input.
    var text = transcriptText.value.trim();
    if (text) {
      formData.append("text", text);
    } else if (fileInput.files && fileInput.files.length > 0) {
      formData.append("file", fileInput.files[0]);
    }
    // If neither has content, let the server return a validation error.

    if (dryRunCheckbox.checked) {
      formData.append("dry_run", "true");
    }

    submitPipeline(formData);
  });

  // -----------------------------------------------------------------------
  // Retry button
  // -----------------------------------------------------------------------
  retryBtn.addEventListener("click", function () {
    if (lastFormData) {
      submitPipeline(lastFormData);
    }
  });
})();
