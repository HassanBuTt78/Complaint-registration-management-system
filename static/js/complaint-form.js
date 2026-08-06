/**
 * Complaint form helpers:
 *  - live character counters
 *  - client-side attachment validation mirroring the server-side rules
 *  - rule-based category / department suggestion (bonus feature)
 *
 * Everything here is advisory. The server re-validates every field.
 */
(function () {
  "use strict";

  var form = document.getElementById("complaint-form");
  if (!form) {
    return;
  }

  var subject = document.getElementById("id_subject");
  var description = document.getElementById("id_description");
  var category = document.getElementById("id_category");
  var department = document.getElementById("id_department");
  var files = document.getElementById("id_attachments");
  var hint = document.getElementById("suggestion-hint");
  var clientError = document.getElementById("client-error");

  var config = form.dataset;
  var maxBytes = parseInt(config.maxUploadBytes || "5242880", 10);
  var maxMb = parseInt(config.maxUploadMb || "5", 10);
  var allowed = (config.allowedExtensions || "pdf,jpg,jpeg,png").split(",");
  var suggestUrl = config.suggestUrl;

  function showError(text) {
    if (!clientError) {
      return;
    }
    clientError.textContent = text;
    clientError.classList.toggle("d-none", !text);
  }

  /* --------------------------------------------------- character counters */
  function bindCounter(field, counterId, min) {
    var counter = document.getElementById(counterId);
    if (!field || !counter) {
      return;
    }
    function update() {
      var length = field.value.trim().length;
      counter.textContent = length + " characters (minimum " + min + ")";
      counter.classList.toggle("text-danger", length > 0 && length < min);
    }
    field.addEventListener("input", update);
    update();
  }

  bindCounter(subject, "subject-counter", 5);
  bindCounter(description, "description-counter", 20);

  /* -------------------------------------------------- attachment checking */
  if (files) {
    files.addEventListener("change", function () {
      var problems = [];
      Array.prototype.forEach.call(files.files, function (file) {
        var ext = (file.name.split(".").pop() || "").toLowerCase();
        if (allowed.indexOf(ext) === -1) {
          problems.push(file.name + " is not a PDF, JPG or PNG file.");
        } else if (file.size > maxBytes) {
          problems.push(file.name + " exceeds the " + maxMb + " MB limit.");
        }
      });
      if (files.files.length > 5) {
        problems.push("You may attach at most 5 files.");
      }
      if (problems.length) {
        files.value = "";
      }
      showError(problems.join(" "));
    });
  }

  /* ------------------------------------------------------ suggestion call */
  var timer = null;

  function applySuggestion(data) {
    return function (event) {
      event.preventDefault();
      if (data.category && category) {
        category.value = data.category;
      }
      if (data.department_id && department) {
        department.value = data.department_id;
      }
      hint.textContent = "Suggestion applied. You can still change it.";
    };
  }

  function requestSuggestion() {
    if (!suggestUrl || !hint) {
      return;
    }
    var subjectValue = subject ? subject.value : "";
    var descriptionValue = description ? description.value : "";
    if ((subjectValue + " " + descriptionValue).trim().length < 12) {
      hint.textContent = "";
      return;
    }

    var url =
      suggestUrl +
      "?subject=" +
      encodeURIComponent(subjectValue) +
      "&description=" +
      encodeURIComponent(descriptionValue);

    fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (data) {
        if (!data) {
          return;
        }
        var parts = [];
        if (data.category && data.category !== "OTHER" && data.confidence >= 0.4) {
          var option = category
            ? category.querySelector('option[value="' + data.category + '"]')
            : null;
          if (option) {
            parts.push("category " + option.textContent.trim());
          }
        }
        if (data.department_name) {
          parts.push("department " + data.department_name);
        }
        if (!parts.length) {
          hint.textContent = "";
          return;
        }

        hint.textContent = "Suggested " + parts.join(" and ") + " - ";
        var link = document.createElement("a");
        link.href = "#";
        link.textContent = "apply";
        link.addEventListener("click", applySuggestion(data));
        hint.appendChild(link);
      })
      .catch(function () {
        /* Suggestions are advisory - stay silent on failure. */
      });
  }

  [subject, description].forEach(function (field) {
    if (!field) {
      return;
    }
    field.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(requestSuggestion, 600);
    });
  });

  /* ------------------------------------------------ submit-time guardrails */
  form.addEventListener("submit", function (event) {
    var errors = [];
    if (subject && subject.value.trim().length < 5) {
      errors.push("Subject must be at least 5 characters.");
    }
    if (description && description.value.trim().length < 20) {
      errors.push("Description must be at least 20 characters.");
    }
    if (department && !department.value) {
      errors.push("Please select a department.");
    }
    if (errors.length) {
      event.preventDefault();
      showError(errors.join(" "));
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  });
})();
