// VoiceNoteMailer.gs
// Polls Gmail for emails with audio attachments, commits them to GitHub.
//
// Email convention:
//   To:      your Gmail address
//   Subject: the-letterboxd-slug   (e.g. "the-green-ray" or "sabrina-1995")
//   Attach:  the .m4a file
//
// Setup:
//   1. Project Settings → Script Properties → add GITHUB_TOKEN
//   2. Triggers → add time-based trigger on processVoiceNoteEmails, every 5 min

var GITHUB_REPO   = 'AntUK88/moviemarginalia';
var GITHUB_BRANCH = 'gh-pages';
var AUDIO_DIR     = 'audio';
var DONE_LABEL    = 'voicenotes-done';

var AUDIO_TYPES = ['audio/', '.m4a', '.mp3', '.aac', '.ogg', '.opus', '.flac', '.wav'];
var SLUG_RE     = /^[a-z0-9]+(-[a-z0-9]+)*$/;


function processVoiceNoteEmails() {
  var token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('GITHUB_TOKEN script property not set');

  var doneLabel = getOrCreateLabel(DONE_LABEL);
  var threads   = GmailApp.search('is:unread has:attachment -label:' + DONE_LABEL, 0, 20);

  threads.forEach(function(thread) {
    thread.getMessages().forEach(function(msg) {
      if (!msg.isUnread()) return;

      var slug = msg.getSubject().trim().toLowerCase().replace(/\s+/g, '-');

      if (!SLUG_RE.test(slug)) {
        Logger.log('Skipping — subject is not a valid slug: ' + slug);
        return;
      }

      var audio = getAudioAttachment(msg);
      if (!audio) {
        Logger.log('Skipping — no audio attachment in: ' + slug);
        return;
      }

      var filename = slug + '.m4a';
      try {
        commitFile(filename, audio, token);
        Logger.log('Committed: ' + filename);
      } catch(e) {
        Logger.log('Error committing ' + filename + ': ' + e);
        return;
      }

      msg.markRead();
      thread.addLabel(doneLabel);
    });
  });
}


function getAudioAttachment(msg) {
  var attachments = msg.getAttachments();
  for (var i = 0; i < attachments.length; i++) {
    var a = attachments[i];
    var type = a.getContentType().toLowerCase();
    var name = a.getName().toLowerCase();
    var isAudio = AUDIO_TYPES.some(function(t) {
      return type.indexOf(t) !== -1 || name.endsWith(t);
    });
    if (isAudio) return a;
  }
  return null;
}


function commitFile(filename, attachment, token) {
  var path    = AUDIO_DIR + '/' + filename;
  var url     = 'https://api.github.com/repos/' + GITHUB_REPO + '/contents/' + encodeURIComponent(path);
  var content = Utilities.base64Encode(attachment.copyBlob().getBytes());
  var headers = {
    'Authorization': 'Bearer ' + token,
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28'
  };

  // Check if file already exists (needed to supply sha for update)
  var sha = null;
  var check = UrlFetchApp.fetch(url + '?ref=' + GITHUB_BRANCH, {
    headers: headers, muteHttpExceptions: true
  });
  if (check.getResponseCode() === 200) {
    sha = JSON.parse(check.getContentText()).sha;
  }

  var body = {
    message: 'Add voice note: ' + filename,
    content: content,
    branch:  GITHUB_BRANCH
  };
  if (sha) body.sha = sha;

  var resp = UrlFetchApp.fetch(url, {
    method: 'PUT',
    headers: headers,
    payload: JSON.stringify(body),
    muteHttpExceptions: true
  });

  var code = resp.getResponseCode();
  if (code !== 200 && code !== 201) {
    throw new Error('GitHub API returned ' + code + ': ' + resp.getContentText());
  }
}


function getOrCreateLabel(name) {
  var labels = GmailApp.getUserLabels();
  for (var i = 0; i < labels.length; i++) {
    if (labels[i].getName() === name) return labels[i];
  }
  return GmailApp.createLabel(name);
}
