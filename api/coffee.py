아래 내용을 검토해서 반영할만한 건 반영해줘.
필수는 아니야.

1. 즉시 수정이 필요한 확정적 버그 (Definite Bugs)
① 구성도 글자(Note) 저장 시 끝 글자 `'s'`가 잘리는 정규식 오타

* 위치: `electron/config-ipc.js` (L364)
* 원인: `cleanNote`에서 문자열 끝 공백(`\s+`)을 제거하려다 백슬래시(`\`)가 누락되었습니다. 

```
js
```

// 현재 코드
const text = n.text.replace(/s+$/, '').slice(0, 2000);
* 증상: 구성도에 추가한 글자가 영문 소문자 `s`로 끝나면(예: `"Web Servers"`, `"k8s"`, `"Prometheus"`) 끝의 `s`가 모두 제거되어 `"Web Server"`, `"k8"`, `"Prometheu"`로 저장되며, 정작 후행 공백은 제거되지 않습니다.
* 해결: `/\s+$/`로 수정해야 합니다.

② SFTP 업로드 감사 로그(접속 기록)에서 파일 개수가 항상 누락됨

* 위치: `electron/session-log.js` (L76) ↔ `electron/sftp.js` (L289)
* 원인: `withTransfer`는 `{ count: t.files, skipped: t.skipped, cancelled }`를 반환하지만, `ACTIONS['sftp:upload']`에서는 존재하지 않는 `r.files` 속성을 참조합니다.   

```
js
```

// 현재 코드 (session-log.js:76)
'sftp:upload': (args, r) => r && ['올리기', `→ ${args[1]}${r.files != null ? ` (파일 ${r.files}개)` : ''}${r.cancelled ? ' (취소됨)' : ''}`],
* 증상: 접속 기록 로그 파일에 업로드한 파일 개수 `(파일 N개)`가 절대 기록되지 않습니다.
* 해결: `r.files`를 `r.count`로 변경해야 합니다(드래그 앤 드롭 업로드인 `sftp:uploadPaths`와 `sftp:download`에도 `r.count`를 함께 표시해주면 더 일관적입니다).

③ 개인 키(`key`) 방식이면서 계정명(`username`)을 비워둔 서버 접속 불가

* 위치: `electron/connect.js` (L142-L205, L229)
* 원인: UI(`ServerDialog.jsx` L289)에서는 계정을 비워 두면 접속할 때 묻도록 허용합니다. 하지만 `login.username`이 빈 문자열(`""`)일 때 `connectDirect`는 `opts.username: ""`인 상태로 `conn.connect(opts)`를 호출하고, 호스트 키 확인 뒤 `authHandler`에서 `askLogin`을 호출하려 합니다.
* 증상: `ssh2` 라이브러리는 `connect(opts)` 호출 시점에 `username`이 비어 있으면 `authHandler`에 도달하기도 전에 예외를 던지거나 인증 단계로 진입하지 못합니다. 또한 개인 키 파일에 패스프레이즈가 걸려 있는데 패스프레이즈를 저장하지 않은 경우에도 로그인 창으로 패스프레이즈를 입력받지 못하고 즉시 `Cannot parse privateKey` 에러로 실패합니다.
* 해결: `login.username`이 비어 있을 때는 `connectDirect`에서 먼저 `askLogin`으로 계정을 입력받거나, `hostVerifier` 직후 `authHandler` 진입이 가능하도록 처리해야 합니다.

④ 열린 세션 탭에서 서버 설정 변경 사항 미반영 (Stale `tab.server`)

* 위치: `renderer/src/App.jsx` (L179, L489)
* 원인: `openSession`에서 탭을 열 때 당시의 `server` 객체 스냅샷을 `tabs` 상태에 그대로 넣어 둡니다.
* 증상: 탭이 열린 상태에서 서버 설정(호스트, 포트, 계정, DB 종류/포트, 권한 전환 옵션 등)을 수정한 뒤 탭의 [재연결] 버튼을 누르면, 메인 프로세스는 새 설정으로 연결하지만 렌더러 탭(`SshTab`, `SftpTab`, `DbTab`, `RdpTab`, `VncTab`)은 여전히 옛날 `tab.server` 스냅샷을 참조하여 잘못된 주소/포트/옵션 칩을 표시하거나, `DbTab`에서 변경된 `dbType`이 반영되지 않습니다.
* 해결: `tabs`에는 `serverId`를 기준으로 최신 `servers.find(s => s.id === t.server.id) || t.server`를 주입하도록 변경하는 것이 안전합니다.

⑤ 위치 이동 모달(`MoveDialog`)에서 자기 하위 폴더가 선택지에 노출됨

* 위치: `renderer/src/MoveDialog.jsx` (L8-L11)
* 원인: `LocationEditor.jsx` (L90)에서는 `folderAndDescendants(folders, f.id)`로 하위 폴더까지 선택지에서 제외하지만, `MoveDialog.jsx`에서는 `f.id !== item.id`만 검사합니다.
* 증상: 폴더 우클릭 → '다른 위치 안으로 옮기기'에서 자신의 하위 폴더를 선택할 수 있고, 선택 시 백엔드 에러 토스트가 발생합니다.

2. 데이터 손실 및 기능 먹통을 유발할 수 있는 중대 잠재 버그
① SFTP 파일 덮어쓰기 실패 시 원본과 임시 파일이 모두 삭제될 위험

* 위치: `electron/sftp.js` (L207-L239, L293-L301)
* 원인:      
   1. `uploadFile`에서 임시 파일 `tmp`를 `t.temps.remote.add(tmp)`에 등록하고 업로드를 마친 뒤 `placeRemote`를 호출합니다.
   2. `ext_openssh_rename`을 지원하지 않는 SFTP 서버(Windows OpenSSH 일부 환경, 상용/임베디드 SFTP 서버 등)에서는 `await call(sftp, 'unlink', remote)`로 원본 파일을 먼저 삭제한 뒤 `await call(sftp, 'rename', tmp, remote)`를 실행합니다.
   3. 만약 `unlink(remote)` 직후 `rename(tmp, remote)`가 실패하면 `t.temps.remote.delete(tmp)`에 도달하지 못한 채 `withTransfer`의 `finally` 블록(L296-L298)으로 이동하여 방금 업로드 완료된 `tmp` 파일까지 `unlink`로 삭제해 버립니다.
* 결과: 기존 원격 파일과 새로 올린 파일이 둘 다 증발할 수 있습니다.
* 해결: `unlink(remote)`를 수행하기 직전에는 `t.temps.remote.delete(tmp)`를 먼저 호출하여, 설령 `rename`이 실패하더라도 업로드된 임시 파일(`tmp`)은 서버에 보존되도록 해야 합니다. 또한 `sftp:writeText`(텍스트 바로 편집 저장)도 바로 `writeFile`로 덮어쓰고 있어 저장 중 연결이 끊기면 원격 설정 파일이 손상될 수 있으므로 `placeRemote` 방식을 쓰는 것이 안전합니다.

② PostgreSQL 커서(`pg-cursor`) 쿼리 에러 시 DB 세션 영구 먹통 (Hang)

* 위치: `electron/db.js` (L144-L150)
* 원인:   

```
js
```

if (limit && returnsRows(sql) && !hasMultipleStatements(sql)) {
const cursor = client.query(new Cursor(sql, [], { rowMode: 'array', types }));
const rows = await cursor.read(limit); // ← 여기서 SQL 에러 발생 시!
const fields = cursor._result?.fields || [];
await cursor.close();
return { columns: fields.map((f) => f.name), rows };
}
* 증상: `SELECT` 문에 문법 오류나 잘못된 컬럼명이 있어 `await cursor.read(limit)`에서 에러가 발생하면 `cursor.close()`가 호출되지 않을 수 있으며, 반대로 `try/finally`로 닫더라도 `pg-cursor` 버전에 따라 상태 정리 전까지 `pg.Client` 큐가 막히는 경우가 있는지 확인하고 안전하게 `cursor.close()`를 보장해야 합니다.

③ DB 스키마 조회(`db:schema`)와 사용자 쿼리(`db:query`)의 단일 커넥션 충돌

* 위치: `renderer/src/DbTab.jsx` (L61), `electron/db.js` (L186-L221, L461-L468)
* 원인: DB 세션 하나당 커넥션 1개(`pool: { max: 1 }` 등)만 사용하는데, `loadSchema()`가 백그라운드에서 최대 3개의 메타데이터 쿼리를 실행하는 동안 사용자가 쿼리를 실행하거나 DDL 실행 후 자동 `loadSchema()`가 겹칠 수 있습니다.
* 증상:      
   * MSSQL: `openMssql`에서 `let current = null` 하나만 유지하므로 동시 실행 시 `current` 참조가 덮어써져 쿼리 취소가 엉뚱하게 동작합니다.
   * Oracle: 단일 커넥션에서 동시에 `execute`가 호출되면 에러가 발생할 수 있습니다.
* 해결: `openDatabase` 계층에서 간단한 비동기 뮤텍스(Promise 체인)를 두어 한 세션 내의 `query()`와 `schema()`가 순차 실행되도록 직렬화하면 모든 드라이버에서 충돌이 방지됩니다.

④ 내장 RDP(`RdpHost.cs`)의 전역 키보드 훅(`WH_KEYBOARD_LL`)과 UI 스레드 `Thread.Sleep`

* 위치: `electron/rdphost/RdpHost.cs` (L385, L406-L437, L469)
* 원인:      
   * `RdpHost.exe`는 `SetWindowsHookEx(13 /* WH_KEYBOARD_LL */, ...)`로 Windows OS 전체의 저수준 키보드 훅을 설치합니다.
   * 그런데 같은 UI 스레드에서 실행되는 `Send` 메서드가 각 키 이벤트마다 `Thread.Sleep(8)`을 수행합니다.
* 증상:      
   1. '클립보드 내용 입력'이나 '텍스트 입력'으로 긴 문자열(예: 200자 = 키 이벤트 약 500개 × 8ms = 4초)을 전송하는 동안 `RdpHost.exe`의 메시지 루프가 최대 수 초간 멈춥니다.
   2. 이 동안 사용자가 실제 키보드를 누르면 OS 전역 훅(`WH_KEYBOARD_LL`) 콜백이 응답하지 못해 PC 전체의 키보드 입력이 멈추거나, Windows의 `LowLevelHooksTimeout`에 의해 훅이 강제로 풀려 이후 Windows 키 전달이 작동하지 않게 됩니다.
   3. RDP 탭을 여러 개 열면 열린 탭 수만큼 전역 키보드 훅이 중복 설치됩니다.
* 해결: `Send`에서 `Thread.Sleep(8)` 대신 비동기 타이머/작업으로 쪼개거나 메시지 루프가 돌도록 처리하고, 원격 화면에 포커스가 있을 때만 훅을 활성화하거나 지연 시간을 최소화해야 합니다.

⑤ 터미널 자동 명령(`runAutoCommands`)의 프롬프트 오인 가능성

* 위치: `electron/terminal.js` (L16, L50-L106)
* 원인: `PROMPT_RE = /[$#>%]\s*$/` 조건과 300ms 출력 정지만으로 프롬프트 및 비밀번호 입력 대기를 판별합니다.
* 증상:      
   * 서버 접속 시 출력되는 배너(MOTD) 중 한 줄이 `#`이나 `>` 등으로 끝나고 네트워크 지연이나 서버 부하로 출력이 300ms 이상 멈추면, 아직 셸이 뜨기 전인데도 자동 명령이나 권한 전환 명령이 전송될 수 있습니다.
   * 또한 자동 명령이 실행되는 도중 사용자가 터미널을 닫거나 재연결해도 백그라운드 IIFE 루프는 `stream`의 `close` 이벤트가 올 때까지 돌아갑니다.

3. 메모리·리소스 누수 및 경쟁 상태 (Resource Leaks & Race Conditions)
① 세션 종료 및 재연결 시 `owners` Map과 `closedEarly` Set의 영구 누수

* 위치: `electron/core.js` (L15, L377-L390), `terminal.js` (L422-L426), `sftp.js` (L42-L48), `db-ipc.js` (L82-L88), `vnc.js` (L50-L56), `rdp.js` (L129-L137)
* 원인:      
   1. 세션을 열 때마다 `own(e, id, kind)`로 `owners` Map에 `${tab.id}#${attempt}`를 추가하지만, 개별 탭을 닫거나 연결이 종료될 때 `owners.delete(id)`를 호출하지 않습니다.
   2. 이미 서버 측에서 끊어졌거나 연결에 실패한 탭을 닫을 때 렌더러의 `useEffect` cleanup이 `*:close` IPC를 보내는데, 이때 이미 세션 맵(`shells`, `sftps`, `dbs`, `vncs`, `rdps`)에 해당 `id`가 없으므로 `else markClosed(id)` 분기를 타서 `closedEarly.add(id)`에 추가됩니다. 이미 종료된 세션이므로 이후 `claim(id)`가 호출되지 않아 `closedEarly`에 영구히 남습니다.
* 해결: 세션이 열리는 과정(`opening` 집합 등)에 있을 때만 `closedEarly`에 넣도록 구분하고, 세션이 완전히 닫힐 때 `owners.delete(id)`와 `closedEarly.delete(id)`를 함께 정리해야 합니다.

② SFTP 스트림 복사(`copyStream`)의 5초 타이머 누수

* 위치: `electron/sftp.js` (L140)
* 원인:   

```
js
```

await Promise.all([from, to].map((st) => (st.closed ? null : new Promise((r) => (st.once('close', r), setTimeout(r, 5000))))));
`st`가 `close` 이벤트로 즉시 닫혀도 `setTimeout(r, 5000)` 타이머가 `clearTimeout` 되지 않고, 반대로 5초 타임아웃이 만료되어도 `st.once('close', r)` 리스너가 해제되지 않습니다.
* 증상: 작은 파일 수천 개가 들어 있는 폴더를 업로드/다운로드할 때 수천 개의 불필요한 타이머가 5초간 메모리에 쌓입니다.

③ 외부 프로그램용 점프 서버 포워딩(`launchForwards`) 미정리 및 설정 변경 미반영

* 위치: `electron/rdp.js` (L170-L180), `electron/main.js` (L48-L55)
* 원인:      
   * 캐시 키가 `${server.id}|${host}|${port}`여서, 사용자가 해당 서버의 `jumpServerId`를 다른 점프 서버로 변경해도 기존 점프 서버 포워딩 포트를 계속 재사용합니다. 키에 `${server.jumpServerId}`를 포함해야 합니다.
   * `main.js`의 `window-all-closed`에서 `launchForwards`의 연결들을 닫는 코드가 빠져 있습니다.

④ 다중 창 환경에서 파일 대화상자의 부모 창(`state.win`) 참조 문제

* 위치: `electron/config-ipc.js` (L212, L225, L502), `electron/sftp.js` (L319, L326, L347), `electron/db-ipc.js` (L93, L102, L112)
* 원인: 모든 `dialog.showOpenDialog` / `showSaveDialog`가 요청을 보낸 창(`winOf(e)`) 대신 전역 `state.win`을 첫 번째 인자로 넘깁니다.
* 증상: 다중 창 사용 시 다른 창에 대화상자가 종속되거나, 만약 `state.win`이 파괴된 직후라면 예외가 발생할 수 있습니다. `winOf(e)`를 사용하고 파괴 여부를 확인하는 헬퍼를 쓰는 것이 안전합니다.

⑤ 터미널 로그 기록(`terminalRecorder`)에서 `\r` 무시로 인한 단일 줄 무한 증식 가능성

* 위치: `electron/session-log.js` (L160-L171)
* 원인: `if (ch === '\r') continue;`로 캐리지 리턴을 무조건 버리고 `\n`이 나올 때까지 `line` 변수에 글자를 계속 이어 붙입니다.
* 증상: 원격 서버에서 `wget`, `curl`, `apt`, `yum`, `docker pull` 등 `\r`만 출력해 같은 줄의 진행률(Progress Bar)을 갱신하는 프로그램을 장시간 실행하면, `\n`이 나올 때까지 수만~수십만 글자가 `line` 하나에 누적되고 로그 파일에도 한 줄에 모든 진행률 텍스트가 이어 붙어 기록됩니다.

4. 구조적 개선점 및 사용성(UX) 향상 제안

1. `ConfirmHost`(`ConfirmDialog.jsx`) 큐 처리 적용:      
   * `HostKeyDialog.jsx`, `LoginDialog.jsx`, `ConflictDialog.jsx`는 모두 `queue` 배열로 복수 요청을 안전하게 직렬 처리하지만, `ConfirmHost`만 단일 `req` 상태를 써서 동시 호출 시 앞선 Promise가 영구 미결(unresolved) 상태가 됩니다. 동일하게 큐 구조로 바꾸면 안전합니다.
2. 목록 보기(`ServerList.jsx` L107-L132)의 빠른 접속 버튼 개선:      
   * 현재 표 목록의 [접속] 열에는 서버 종류나 설정과 무관하게 `SSH` / `SFTP` / `Telnet` 버튼만 고정 표시됩니다. Windows 서버(`rdp`)나 DB 서버(`db`), VNC 서버(`vnc`)의 경우 해당 서버의 기본 프로토콜 버튼을 우선 표시하거나 서버 특성에 맞는 버튼을 노출하면 사용성이 크게 좋아집니다.
3. MySQL 대용량 조회 시 스트리밍 중단 처리 (`electron/db.js` L102-L106):      
   * PostgreSQL은 커서로 `MAX_ROWS + 1`개만 읽고 닫으며, MSSQL도 `limit` 도달 시 `req.cancel()`을 호출하지만, MySQL/MariaDB는 `rows.length < limit` 이후에도 서버가 보내는 나머지 수백만 행을 네트워크로 끝까지 다 흘려보낼 때까지 쿼리가 끝나지 않습니다.
4. 로컬 포트 포워딩(`electron/connect.js` L292-L317, `terminal.js` L217-L241) 소켓 정리:      
   * `listener.close()` 호출 시 이미 연결되어 있는 하위 `sock`들도 즉시 `destroy()`하도록 열린 소켓 `Set`을 관리하면 터널/세션 종료 시 리소스가 깔끔하게 회수됩니다.
