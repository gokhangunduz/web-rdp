(async function () {
  function decode_int8(data, off) {
    return data[off];
  }

  function decode_int16(data, off) {
    return data[off] | (data[off + 1] << 8);
  }

  function encode_int8(i, arr, off) {
    arr[off] = i & 0xff;
  }

  function encode_int16(i, arr, off) {
    arr[off] = i & 0xff;
    arr[off + 1] = (i >> 8) & 0xff;
  }

  // ws:// on http pages, wss:// on https pages
  function socketUrl(path) {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${scheme}//${window.location.host}/${path}`;
  }

  var toastsElement = document.getElementById("toasts");

  // Small non-blocking message at the top of the page
  function showToast(message, seconds = 3) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    toastsElement.appendChild(toast);

    setTimeout(function () {
      toast.classList.add("hide");
      setTimeout(() => toast.remove(), 300);
    }, seconds * 1000);
  }

  var app = {
    viewSocket: null,
    workerLoopTs: 0,
    workerLoopShouldRun: false,
    keepAlive: true,
    viewPromise: null,
    inputPromise: null,
    remote: {
      width: 0,
      height: 0,
    },
    viewport: {
      width: 0,
      height: 0,
    },
    props: {
      quality: 60,
      fps: 50,
      ips: 60,
    },
  };

  function getProp(name) {
    return app.props[name];
  }

  app.canvas = document.getElementById("display");
  app.canvasContext = app.canvas.getContext("2d");
  var netstatElement = document.querySelector("#netstat");
  app.startConnection = async function () {
    console.log("startConnection() : enter");
    if (app.isConnectionRunning) {
      console.log("startConnection() : unstack");
      return;
    }

    app.isConnectionRunning = true;
    netstatElement.textContent = "";
    app.viewPromise = new Promise((resolve, _) => {
      var makeViewConnection = function () {
        var lastFrameRequestTS = null;

        const requestFrame = function () {
          if (!app.keepAlive || mySocketRef.readyState === WebSocket.CLOSED) {
            try {
              mySocketRef.close();
            } catch {}
            return;
          }

          let requestFrame__buffer = new Uint8Array(1 + 2 + 2 + 1);

          try {
            encode_int8(0x01, requestFrame__buffer, 0);
            const viewport_width = Math.max(
              Math.min(window.innerWidth, 65535),
              1
            );
            const viewport_height = Math.max(
              Math.min(window.innerHeight, 65535),
              1
            );
            const quality = Math.max(Math.min(getProp("quality"), 100), 1);

            encode_int16(viewport_width, requestFrame__buffer, 1);
            encode_int16(viewport_height, requestFrame__buffer, 3);
            encode_int8(quality, requestFrame__buffer, 5);

            lastFrameRequestTS = Date.now();
            mySocketRef.send(requestFrame__buffer.buffer);
          } catch (e) {
            console.error(e);
          }
        };

        // Only called for full frames: a frame request carries the window
        // size, so the server always answers a resize with a full repaint
        var updateSize = function () {
          if (
            app.canvas.width != window.innerWidth ||
            app.canvas.height != window.innerHeight
          ) {
            app.canvas.width = window.innerWidth;
            app.canvas.height = window.innerHeight;
          }
        };
        var interframeDelay = 1000.0 / getProp("fps");

        // Top left corner of the frame, which is centered on the canvas
        var frameOrigin = function () {
          return [
            Math.round((app.canvas.width - app.viewport.width) / 2),
            Math.round((app.canvas.height - app.viewport.height) / 2),
          ];
        };

        function viewSocketMessage(msg) {
          if (!app.keepAlive || mySocketRef.readyState === WebSocket.CLOSED) {
            try {
              mySocketRef.close();
            } catch {}
            return;
          }
          if (!(msg.data instanceof ArrayBuffer)) return;

          var data = new Uint8Array(msg.data);
          if (decode_int8(data, 0) != 0x02) return;

          var frameRTT = Date.now() - lastFrameRequestTS;
          netstatElement.textContent = `${frameRTT}ms`;

          // Ask for the next frame, but not faster than the configured fps
          var requestNext = function () {
            setTimeout(requestFrame, Math.max(0, interframeDelay - frameRTT));
          };

          if (data.length < 6) return requestNext();

          app.remote.width = decode_int16(data, 1);
          app.remote.height = decode_int16(data, 3);
          var frame_type = decode_int8(data, 5);

          if (frame_type === 0x01) {
            createImageBitmap(new Blob([data.subarray(6)], { type: "image/jpeg" }))
              .then(function (frame) {
                updateSize();
                app.viewport.width = frame.width;
                app.viewport.height = frame.height;
                var [x, y] = frameOrigin();
                app.canvasContext.drawImage(frame, x, y);
                frame.close();
              })
              .catch(console.error)
              .finally(requestNext);
          } else if (frame_type === 0x02 && data.length > 10) {
            var crop_x = decode_int16(data, 6);
            var crop_y = decode_int16(data, 8);
            createImageBitmap(new Blob([data.subarray(10)], { type: "image/webp" }))
              .then(function (frame) {
                var [x, y] = frameOrigin();
                app.canvasContext.drawImage(frame, x + crop_x, y + crop_y);
                frame.close();
              })
              .catch(console.error)
              .finally(requestNext);
          } else {
            requestNext(); // nothing changed
          }
        }
        var titleSetTimeout = null;

        function viewSocketOpen(event) {
          if (!app.keepAlive || mySocketRef.readyState === WebSocket.CLOSED) {
            try {
              mySocketRef.close();
            } catch {}
            return;
          }

          titleSetTimeout = setTimeout(function () {
            document.title = "web-rdp (Connected)";
          }, 1000);
          requestFrame();
        }

        function viewSocketClose(event) {
          if (event.code !== 4001) {
            showToast("Screen connection closed, reconnecting...");
          }
          clearTimeout(titleSetTimeout);
          document.title = "web-rdp (Disconnected)";
          if (app.keepAlive) {
            setTimeout(
              function () {
                if (!app.keepAlive) resolve();
                else makeViewConnection();
              },
              event.code === 4001 ? 5000 : 1000
            );
          } else resolve();
        }

        var mySocketRef = new WebSocket(socketUrl("streamWS"));
        mySocketRef.binaryType = "arraybuffer";
        mySocketRef.onmessage = viewSocketMessage;
        mySocketRef.onopen = viewSocketOpen;
        mySocketRef.onclose = viewSocketClose;
        app.viewSocket = mySocketRef;
      };
      makeViewConnection();
    });
    app.inputPromise = new Promise((resolve, _) => {
      var makeInputConnection = async function () {
        function inputSocketMessage(msg) {
          if (!app.keepAlive) {
            try {
              app.viewSocket.close();
            } catch {}
          }
          if (msg.data instanceof ArrayBuffer) {
            var data = new Uint8Array(msg.data);
            delete data;
          }
        }

        function inputSocketOpen(event) {
          if (!app.keepAlive || mySocketRef.readyState === WebSocket.CLOSED) {
            try {
              mySocketRef.close();
            } catch {}
            return;
          }
          startInputLoop();
        }

        function inputSocketClose(event) {
          stopInputLoop();
          if (event.code !== 4001) {
            showToast("Input connection closed, reconnecting...");
          }
          if (app.keepAlive) {
            setTimeout(
              function () {
                if (!app.keepAlive) {
                  resolve();
                } else makeInputConnection();
              },
              event.code === 4001 ? 5000 : 1000
            );
          } else resolve();
        }

        // Load the key table first: the handlers below are only defined after
        // this point and the socket may open as soon as it is created
        let jsToPyKeys;
        try {
          jsToPyKeys = await fetch("/keys.json").then((res) => res.json());
        } catch (e) {
          console.error(e);
          showToast("Could not load key map, retrying...");
          setTimeout(makeInputConnection, 2000);
          return;
        }

        var inputEvents = [];
        var flushTimer = null;
        var lastFlush = 0;

        // Queue an event and send the queue at most `ips` times per second.
        // The first event after a quiet period goes out immediately.
        function enqueue(inputEvent) {
          inputEvents.push(inputEvent);
          if (flushTimer !== null) return;

          const wait = Math.max(
            0,
            lastFlush + 1000.0 / getProp("ips") - Date.now()
          );
          flushTimer = setTimeout(flushInput, wait);
        }

        function flushInput() {
          flushTimer = null;
          if (!inputEvents.length) return;

          const events = inputEvents;
          inputEvents = [];
          if (!app.keepAlive || mySocketRef.readyState !== WebSocket.OPEN) {
            return; // the connection is gone, stale input must not be replayed
          }

          try {
            const body = new TextEncoder().encode(JSON.stringify(events));
            const packet = new Uint8Array(1 + body.length);
            encode_int8(0x03, packet, 0);
            packet.set(body, 1);
            mySocketRef.send(packet.buffer);
            lastFlush = Date.now();
          } catch (e) {
            console.error(e);
          }
        }

        // Keys and mouse buttons currently held down
        const pressedKeys = new Set();
        const pressedButtons = new Set();
        let lastRemotePos = null;

        // Browser coordinates -> pixels of the remote screen, null while no frame arrived
        function toRemote(event) {
          const { clientWidth, clientHeight } = app.canvas;
          const { width, height } = app.viewport;
          const { width: remoteWidth, height: remoteHeight } = app.remote;
          if (!width || !height || !remoteWidth || !remoteHeight) return null;

          // The frame is centered on the canvas, same rounding as when drawing
          const rectX = Math.round((clientWidth - width) / 2);
          const rectY = Math.round((clientHeight - height) / 2);

          const x = Math.round(((event.clientX - rectX) * remoteWidth) / width);
          const y = Math.round(((event.clientY - rectY) * remoteHeight) / height);

          lastRemotePos = [
            Math.max(0, Math.min(remoteWidth - 1, x)),
            Math.max(0, Math.min(remoteHeight - 1, y)),
          ];
          return lastRemotePos;
        }

        const mouseMoveEvent = function (event) {
          const pos = toRemote(event);
          if (!pos) return;

          // Only the latest pointer position matters, replace a queued move
          const last = inputEvents[inputEvents.length - 1];
          if (last && last[0] === 0) inputEvents.pop();
          enqueue([0, ...pos]);
        };

        const mouseDownEvent = function (event) {
          event.preventDefault();
          event.stopPropagation();

          const pos = toRemote(event);
          if (!pos) return;

          pressedButtons.add(event.button);
          enqueue([1, ...pos, event.button]);
        };

        const mouseUpEvent = function (event) {
          event.preventDefault();
          event.stopPropagation();

          // Ignore releases of buttons that were not pressed on this page
          if (!pressedButtons.has(event.button)) return;

          const pos = toRemote(event);
          if (!pos) return;

          pressedButtons.delete(event.button);
          enqueue([2, ...pos, event.button]);
        };

        const mouseScrollEvent = function (event) {
          event.preventDefault();

          // Firefox reports lines or pages instead of pixels on some devices
          const unit = [1, 40, 800][event.deltaMode] || 1;
          const amount = Math.round(-event.deltaY * unit);

          const pos = toRemote(event);
          if (pos && amount) enqueue([3, ...pos, amount]);
        };

        const mouseContextEvent = function (event) {
          event.preventDefault();
          event.stopPropagation();
          return false;
        };

        const keyDownEvent = function (event) {
          // Keys without a mapping stay with the browser
          if (!(event.code in jsToPyKeys)) return;

          event.preventDefault();
          event.stopPropagation();

          pressedKeys.add(event.code);
          enqueue([4, jsToPyKeys[event.code]]);
        };

        const keyUpEvent = function (event) {
          if (!(event.code in jsToPyKeys)) return;

          event.preventDefault();
          event.stopPropagation();

          // macOS never reports the release of keys pressed while Meta is
          // held, so letting go of Meta releases everything to avoid stuck keys
          if (event.code === "MetaLeft" || event.code === "MetaRight") {
            releaseAllInputs();
            return;
          }

          pressedKeys.delete(event.code);
          enqueue([5, jsToPyKeys[event.code]]);
        };

        // Let go of every key and button held down, e.g. when the tab loses focus
        const releaseAllInputs = function () {
          for (const code of pressedKeys) {
            enqueue([5, jsToPyKeys[code]]);
          }
          pressedKeys.clear();

          if (lastRemotePos) {
            for (const button of pressedButtons) {
              enqueue([2, ...lastRemotePos, button]);
            }
          }
          pressedButtons.clear();
        };

        function startInputLoop() {
          app.canvas.addEventListener("mousemove", mouseMoveEvent);
          app.canvas.addEventListener("wheel", mouseScrollEvent);
          app.canvas.addEventListener("mousedown", mouseDownEvent);
          // On window so releasing outside of the canvas is seen too
          window.addEventListener("mouseup", mouseUpEvent);
          app.canvas.addEventListener("contextmenu", mouseContextEvent);
          document.addEventListener("keydown", keyDownEvent);
          document.addEventListener("keyup", keyUpEvent);
          window.addEventListener("blur", releaseAllInputs);
        }

        function stopInputLoop() {
          app.canvas.removeEventListener("mousemove", mouseMoveEvent);
          app.canvas.removeEventListener("wheel", mouseScrollEvent);
          app.canvas.removeEventListener("mousedown", mouseDownEvent);
          window.removeEventListener("mouseup", mouseUpEvent);
          app.canvas.removeEventListener("contextmenu", mouseContextEvent);
          document.removeEventListener("keydown", keyDownEvent);
          document.removeEventListener("keyup", keyUpEvent);
          window.removeEventListener("blur", releaseAllInputs);
          pressedKeys.clear();
          pressedButtons.clear();
          clearTimeout(flushTimer);
          flushTimer = null;
          inputEvents = [];
        }

        var mySocketRef = new WebSocket(socketUrl("inputWS"));
        mySocketRef.binaryType = "arraybuffer";
        mySocketRef.onmessage = inputSocketMessage;
        mySocketRef.onopen = inputSocketOpen;
        mySocketRef.onclose = inputSocketClose;
        app.inputSocket = mySocketRef;
      };
      makeInputConnection();
    });
    console.log("startConnection() : exit");
  };

  app.startConnection();
})();
