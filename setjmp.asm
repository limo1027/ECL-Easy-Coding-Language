.code

; int64_t runtime_setjmp(jmp_buf_t* env)
; 参数 env 在 rcx 中
; 返回 0 表示首次调用，返回非 0 表示从 longjmp 恢复
runtime_setjmp PROC
    ; 保存非易失性寄存器和栈指针
    mov [rcx + 0], rbx
    mov [rcx + 8], rbp
    mov [rcx + 16], rdi
    mov [rcx + 24], rsi
    mov [rcx + 32], rsp
    mov [rcx + 40], r12
    mov [rcx + 48], r13
    mov [rcx + 56], r14
    mov [rcx + 64], r15
    
    ; 保存返回地址 (RIP)
    mov rax, [rsp]
    mov [rcx + 72], rax
    
    ; 返回 0
    xor eax, eax
    ret
runtime_setjmp ENDP

; void runtime_longjmp(jmp_buf_t* env, int64_t val)
; 参数 env 在 rcx，val 在 rdx
runtime_longjmp PROC
    ; 恢复非易失性寄存器
    mov rbx, [rcx + 0]
    mov rbp, [rcx + 8]
    mov rdi, [rcx + 16]
    mov rsi, [rcx + 24]
    mov rsp, [rcx + 32]
    mov r12, [rcx + 40]
    mov r13, [rcx + 48]
    mov r14, [rcx + 56]
    mov r15, [rcx + 64]
    
    ; 恢复 RIP，并跳转过去
    mov rax, [rcx + 72]
    mov [rsp], rax
    
    ; 返回 val
    mov rax, rdx
    ret
runtime_longjmp ENDP

END