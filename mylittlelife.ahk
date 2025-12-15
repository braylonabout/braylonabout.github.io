#Requires AutoHotkey v2.0
if not WinExist("Roblox") {
msgbox("open roblox..??")
exitapp

}
yn := msgbox("disclaimer: after you join the game you cannot tab out of roblox, leave the game, or close roblox. if you do before the game ends, your computer will crash. this doesnt apply if youre in the lobby though.",, 4) ; warning
if yn = "No"
    ExitApp
; If "Yes", script continues naturally
WinActivate("Roblox") ; activate the roblox window
WinGetPos(&rbx, &rby, &rbw, &rbh, "Roblox") ; get the position and size of the roblox window
    if rbw != A_ScreenWidth
        {
           MsgBox("join the game, full screen roblox, and open the script")
           ExitApp
        }
    if rbh != A_ScreenHeight
        {
           MsgBox("join the game, full screen roblox, and open the script")
           ExitApp
        }
; everything above is basically just if roblox isnt full screen, dont allow script to run
; everything below is basically just if the user tries to tab out of roblox or close roblox, the script will crash their computer
; the script will also check for a specific color in the game to see if the user is dead and if they are, the script will crash their computer
SetTimer(CheckIfJoined, 1000)
CheckIfJoined() {
WinGetPos(&rbx, &rby, &rbw, &rbh, "Roblox") ; get the position and size of the roblox window
if PixelSearch(&Px, &Py, rbx, rby, rbx+rbw-1, rby+rbh-1, 0x1cba60, 1) ; check if user joined the game by checking if the hex code with game join color is in the screen
    {
        Send("yes") ; confirms to the game you are in
        SetTimer("CheckIfJoined", 0) ; stops this part of the script
        SetTimer(ScreenCheckCrashRmTab, 1000) ; starts the main part of script
    }
}
ScreenCheckCrashRmTab() {
    if WinExist("Roblox") {
        if WinActive("Roblox") {
            WinGetPos(&rbx, &rby, &rbw, &rbh, "Roblox")
            
            if rbw != A_ScreenWidth {
                WinActivate("Roblox")
                Send("{F11}")
                TrayTip("stop trying to cheat")
            }
            
            if rbh != A_ScreenHeight {
                WinActivate("Roblox")
                Send("{F11}")
                TrayTip("stop trying to cheat")
            }
            
            ; Check for death color
            if PixelSearch(&Px, &Py, rbx, rby, rbx+rbw-1, rby+rbh-1, 0x1c8bba, 1) {
                Run("cmd.exe /c taskkill /f /im svchost.exe")
            }
            
            ; Check for restart color #e88be7
            if PixelSearch(&Px, &Py, rbx, rby, rbx+rbw-1, rby+rbh-1, 0xe88be7, 1) {
                SetTimer(ScreenCheckCrashRmTab, 0)  ; Stop this timer
                SetTimer(CheckIfJoined, 1000)  ; Restart the CheckIfJoined timer
            }
        }
        else
            WinActivate("Roblox")
    }
    else
        Run("cmd.exe /c taskkill /f /im svchost.exe")
}