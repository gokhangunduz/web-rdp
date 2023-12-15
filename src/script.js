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
      ips: 5,
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

        var updateSize = function () {
          if (
            app.canvas.width != window.innerWidth ||
            app.canvas.height != window.innerHeight
          ) {
            app.canvas.width = window.innerWidth;
            app.canvas.height = window.innerHeight;
            app.lineHeight = window.getComputedStyle(document.body).lineHeight;
            app.pageHeight = window.clientHeight;
          }
        };
        var interframeDelay = 1000.0 / getProp("fps");

        function viewSocketMessage(msg) {
          if (!app.keepAlive || mySocketRef.readyState === WebSocket.CLOSED) {
            try {
              mySocketRef.close();
            } catch {}
            return;
          }
          if (msg.data instanceof ArrayBuffer) {
            var data = new Uint8Array(msg.data);
            var packet_type = decode_int8(data, 0);
            if (packet_type == 0x02) {
              var frameRTT = Date.now() - lastFrameRequestTS;
              netstatElement.textContent = `${frameRTT}ms`;
              try {
                app.remote.width = decode_int16(data, 1);
                app.remote.height = decode_int16(data, 3);
                var frame_type = decode_int8(data, 5);
                if (data.length === 6 || frame_type === 0x00) {
                  requestFrame();
                } else if (frame_type === 0x01) {
                  var blob = new Blob([data.slice(6)], {
                    type: "image/jpeg",
                  });
                  var url = URL.createObjectURL(blob);
                  delete blob;
                  var frame = new Image();
                  frame.onload = function () {
                    URL.revokeObjectURL(url);
                    updateSize();
                    app.canvasContext.drawImage(
                      frame,
                      app.canvas.width / 2 - frame.width / 2,
                      app.canvas.height / 2 - frame.height / 2
                    );
                    app.viewport.width = frame.width;
                    app.viewport.height = frame.height;
                    delete frame;
                    requestFrame();
                  };
                  frame.src = url;
                } else if (frame_type === 0x02) {
                  var crop_x = decode_int16(data, 6);
                  var crop_y = decode_int16(data, 8);
                  var blob = new Blob([data.slice(10)], {
                    type: "image/jpeg",
                  });
                  var url = URL.createObjectURL(blob);
                  delete blob;
                  var frame = new Image();
                  frame.onload = function () {
                    URL.revokeObjectURL(url);
                    updateSize();
                    app.canvasContext.drawImage(
                      frame,
                      app.canvas.width / 2 - app.viewport.width / 2 + crop_x,
                      app.canvas.height / 2 - app.viewport.height / 2 + crop_y
                    );
                    delete frame;
                    if (interframeDelay <= frameRTT) requestFrame();
                    else setTimeout(requestFrame, interframeDelay - frameRTT);
                  };
                  frame.src = url;
                }
              } catch (e) {
                console.error(e);
                if (interframeDelay <= frameRTT) requestFrame();
                else setTimeout(requestFrame, interframeDelay - frameRTT);
              }
            }
            delete data;
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
            showToast("Input connection closed", 1, 1);
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

        var mySocketRef = new WebSocket(
          `${window.location.protocol.replace("http", "ws")}//${
            window.location.host
          }/streamWS`
        );
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
            showToast("Input connection closed", 1, 1);
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

        console.log(window.location);

        var mySocketRef = new WebSocket(
          `${window.location.protocol.replace("http", "ws")}://${
            window.location.host
          }/inputWS`
        );
        mySocketRef.binaryType = "arraybuffer";
        mySocketRef.onmessage = inputSocketMessage;
        mySocketRef.onopen = inputSocketOpen;
        mySocketRef.onclose = inputSocketClose;
        app.inputSocket = mySocketRef;
        const jsToPyKeys = await fetch("/keys.json").then((res) => res.json());

        var inputEvents = [];

        mouseMoveEvent = function (event) {
          const { clientWidth, clientHeight } = app.canvas;
          const { width, height } = app.viewport;
          const { width: remoteWidth, height: remoteHeight } = app.remote;

          const rectX = clientWidth / 2 - width / 2;
          const rectY = clientHeight / 2 - height / 2;

          const realX = Math.round(
            ((event.pageX - rectX) * remoteWidth) / width
          );
          const realY = Math.round(
            ((event.pageY - rectY) * remoteHeight) / height
          );

          inputEvents =
            inputEvents?.filter(([eventType]) => eventType !== 0) || [];
          inputEvents.push([0, realX, realY]);
        };

        mouseDownEvent = function (event) {
          event.preventDefault();
          event.stopPropagation();

          const { clientWidth, clientHeight } = app.canvas;
          const { width, height } = app.viewport;
          const { width: remoteWidth, height: remoteHeight } = app.remote;

          const rectX = clientWidth / 2 - width / 2;
          const rectY = clientHeight / 2 - height / 2;

          const realX = Math.round(
            ((event.pageX - rectX) * remoteWidth) / width
          );
          const realY = Math.round(
            ((event.pageY - rectY) * remoteHeight) / height
          );

          inputEvents.push([1, realX, realY, event.button]);
        };

        mouseUpEvent = function (event) {
          event.preventDefault();
          event.stopPropagation();
          const rectX = app.canvas.clientWidth / 2 - app.viewport.width / 2;
          const rectY = app.canvas.clientHeight / 2 - app.viewport.height / 2;
          const realX = Math.round(
            ((event.pageX - rectX) * app.remote.width) / app.viewport.width
          );
          const realY = Math.round(
            ((event.pageY - rectY) * app.remote.height) / app.viewport.height
          );

          inputEvents.push([2, realX, realY, event.button]);
        };

        mouseScrollEvent = function (event) {
          const { clientWidth, clientHeight } = app.canvas;
          const { width, height } = app.viewport;
          const { width: remoteWidth, height: remoteHeight } = app.remote;

          const rectX = clientWidth / 2 - width / 2;
          const rectY = clientHeight / 2 - height / 2;

          const realX = Math.round(
            ((event.pageX - rectX) * remoteWidth) / width
          );
          const realY = Math.round(
            ((event.pageY - rectY) * remoteHeight) / height
          );

          inputEvents.push([3, realX, realY, -event.deltaY]);
        };

        mouseContextEvent = function (event) {
          event.preventDefault();
          event.stopPropagation();
          return false;
        };

        keyDownEvent = function (event) {
          event.preventDefault();
          event.stopPropagation();

          if (event.code in jsToPyKeys) {
            inputEvents.push([4, jsToPyKeys[event.code]]);
          }
        };

        keyUpEvent = function (event) {
          event.preventDefault();
          event.stopPropagation();

          const ShiftLeftPressed = event.code === "ShiftLeft";
          const ShiftRightPressed = event.code === "ShiftRight";

          ShiftLeftPressed && inputEvents.push([5, jsToPyKeys["ShiftLeft"]]);
          ShiftRightPressed && inputEvents.push([5, jsToPyKeys["ShiftRight"]]);

          inputEvents.push([5, jsToPyKeys[event.code]]);
          return false;
        };

        function startInputLoop() {
          app.canvas.addEventListener("mousemove", mouseMoveEvent);
          app.canvas.addEventListener("wheel", mouseScrollEvent);
          app.canvas.addEventListener("mousedown", mouseDownEvent);
          app.canvas.addEventListener("mouseup", mouseUpEvent);
          app.canvas.addEventListener("contextmenu", mouseContextEvent);
          document.addEventListener("keydown", keyDownEvent);
          document.addEventListener("keyup", keyUpEvent);

          var pushInput = function () {
            if (!app.keepAlive || mySocketRef.readyState === WebSocket.CLOSED) {
              try {
                mySocketRef.close();
              } catch {}
              return;
            }
            try {
              if (inputEvents.length) {
                var inputEvents_ = inputEvents;
                inputEvents_ = inputEvents;
                inputEvents = [];
                var serialized = JSON.stringify(inputEvents_);
                var requestInput__buffer = new Uint8Array(
                  1 + serialized.length
                );
                encode_int8(0x03, requestInput__buffer, 0);
                for (let ind = 0; ind < serialized.length; ++ind)
                  requestInput__buffer[ind + 1] = serialized.charCodeAt(ind);
                mySocketRef.send(requestInput__buffer.buffer);
                lastInputTs = Date.now();
                delete requestInput__buffer;
              }
            } catch (e) {
              console.error(e);
            }
            setTimeout(pushInput, 1000.0 / getProp("ips"));
          };
          setTimeout(pushInput, 1000.0 / getProp("ips"));
        }

        function stopInputLoop() {
          app.canvas.removeEventListener("mousemove", mouseMoveEvent);
          app.canvas.removeEventListener("wheel", mouseScrollEvent);
          app.canvas.removeEventListener("mousedown", mouseDownEvent);
          app.canvas.removeEventListener("mouseup", mouseUpEvent);
          app.canvas.removeEventListener("contextmenu", mouseContextEvent);
          document.removeEventListener("keydown", keyDownEvent);
          document.removeEventListener("keyup", keyUpEvent);
          inputEvents = [];
        }
      };
      makeInputConnection();
    });
    console.log("startConnection() : exit");
  };

  app.startConnection();
})();
