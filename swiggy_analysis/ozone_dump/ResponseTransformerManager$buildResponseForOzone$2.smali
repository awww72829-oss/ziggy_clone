.class final Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;
.super Lkotlin/coroutines/jvm/internal/SuspendLambda;
.source "SourceFile"

# interfaces
.implements Lkotlin/jvm/functions/c;


# annotations
.annotation system Ldalvik/annotation/Signature;
    value = {
        "Lkotlin/coroutines/jvm/internal/SuspendLambda;",
        "Lkotlin/jvm/functions/c;"
    }
.end annotation

.annotation runtime Lkotlin/Metadata;
    d1 = {
        "\u0000\u001c\n\u0002\u0010\u0000\n\u0000\n\u0002\u0018\u0002\n\u0002\u0018\u0002\n\u0002\u0010\u0003\n\u0000\n\u0002\u0010\u0002\n\u0002\u0008\u0002\u0010\u0007\u001a\u00020\u0006\"\u0008\u0008\u0000\u0010\u0001*\u00020\u0000*\u000e\u0012\n\u0012\u0008\u0012\u0004\u0012\u00028\u00000\u00030\u00022\u0006\u0010\u0005\u001a\u00020\u0004H\n\u00a2\u0006\u0004\u0008\u0007\u0010\u0008"
    }
    d2 = {
        "",
        "M",
        "Lkotlinx/coroutines/flow/h;",
        "Lin/swiggy/android/tejas/f;",
        "",
        "it",
        "",
        "<anonymous>",
        "(Lkotlinx/coroutines/flow/h;Ljava/lang/Throwable;)V"
    }
    k = 0x3
    mv = {
        0x2,
        0x2,
        0x0
    }
.end annotation

.annotation runtime Lkotlin/coroutines/jvm/internal/c;
    c = "in.swiggy.android.tejas.ResponseTransformerManager$buildResponseForOzone$2"
    f = "ResponseTransformerManager.kt"
    l = {
        0x87,
        0x88
    }
    m = "invokeSuspend"
    v = 0x1
.end annotation


# instance fields
.field final synthetic $exceptionTransformer:Lin/swiggy/android/tejas/coroutineUtils/c;
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "Lin/swiggy/android/tejas/coroutineUtils/c;"
        }
    .end annotation
.end field

.field I$0:I

.field private synthetic L$0:Ljava/lang/Object;

.field synthetic L$1:Ljava/lang/Object;

.field L$2:Ljava/lang/Object;

.field label:I


# direct methods
.method public constructor <init>(Lin/swiggy/android/tejas/coroutineUtils/c;Lkotlin/coroutines/d;)V
    .locals 0

    iput-object p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->$exceptionTransformer:Lin/swiggy/android/tejas/coroutineUtils/c;

    const/4 p1, 0x3

    invoke-direct {p0, p1, p2}, Lkotlin/coroutines/jvm/internal/SuspendLambda;-><init>(ILkotlin/coroutines/d;)V

    return-void
.end method


# virtual methods
.method public final invoke(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;
    .locals 1

    .line 1
    check-cast p1, Lkotlinx/coroutines/flow/h;

    .line 2
    .line 3
    check-cast p2, Ljava/lang/Throwable;

    .line 4
    .line 5
    check-cast p3, Lkotlin/coroutines/d;

    .line 6
    .line 7
    new-instance v0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;

    .line 8
    .line 9
    iget-object p0, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->$exceptionTransformer:Lin/swiggy/android/tejas/coroutineUtils/c;

    .line 10
    .line 11
    invoke-direct {v0, p0, p3}, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;-><init>(Lin/swiggy/android/tejas/coroutineUtils/c;Lkotlin/coroutines/d;)V

    .line 12
    .line 13
    .line 14
    iput-object p1, v0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->L$0:Ljava/lang/Object;

    .line 15
    .line 16
    iput-object p2, v0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->L$1:Ljava/lang/Object;

    .line 17
    .line 18
    sget-object p0, Lkotlin/Unit;->a:Lkotlin/Unit;

    .line 19
    .line 20
    invoke-virtual {v0, p0}, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;

    .line 21
    .line 22
    .line 23
    move-result-object p0

    .line 24
    return-object p0
.end method

.method public final invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;
    .locals 7

    .line 1
    iget-object v0, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->L$0:Ljava/lang/Object;

    .line 2
    .line 3
    check-cast v0, Lkotlinx/coroutines/flow/h;

    .line 4
    .line 5
    iget-object v1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->L$1:Ljava/lang/Object;

    .line 6
    .line 7
    check-cast v1, Ljava/lang/Throwable;

    .line 8
    .line 9
    sget-object v2, Lkotlin/coroutines/intrinsics/CoroutineSingletons;->COROUTINE_SUSPENDED:Lkotlin/coroutines/intrinsics/CoroutineSingletons;

    .line 10
    .line 11
    iget v3, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->label:I

    .line 12
    .line 13
    const/4 v4, 0x2

    .line 14
    const/4 v5, 0x1

    .line 15
    const/4 v6, 0x0

    .line 16
    if-eqz v3, :cond_2

    .line 17
    .line 18
    if-eq v3, v5, :cond_1

    .line 19
    .line 20
    if-ne v3, v4, :cond_0

    .line 21
    .line 22
    goto :goto_0

    .line 23
    :cond_0
    const-string p0, "call to \'resume\' before \'invoke\' with coroutine"

    .line 24
    .line 25
    invoke-static {p0}, Lk;->e(Ljava/lang/String;)V

    .line 26
    .line 27
    .line 28
    return-object v6

    .line 29
    :cond_1
    iget-object p0, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->L$2:Ljava/lang/Object;

    .line 30
    .line 31
    check-cast p0, Lin/swiggy/android/tejas/coroutineUtils/c;

    .line 32
    .line 33
    :goto_0
    invoke-static {p1}, Lkotlin/l;->b(Ljava/lang/Object;)V

    .line 34
    .line 35
    .line 36
    goto :goto_2

    .line 37
    :cond_2
    invoke-static {p1}, Lkotlin/l;->b(Ljava/lang/Object;)V

    .line 38
    .line 39
    .line 40
    iget-object p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->$exceptionTransformer:Lin/swiggy/android/tejas/coroutineUtils/c;

    .line 41
    .line 42
    if-eqz p1, :cond_3

    .line 43
    .line 44
    invoke-virtual {p1, v1}, Lin/swiggy/android/tejas/coroutineUtils/e;->b(Ljava/lang/Object;)Lkotlinx/coroutines/flow/g;

    .line 45
    .line 46
    .line 47
    move-result-object p1

    .line 48
    new-instance v3, Lin/swiggy/android/tejas/p;

    .line 49
    .line 50
    invoke-direct {v3, v0}, Lin/swiggy/android/tejas/p;-><init>(Lkotlinx/coroutines/flow/h;)V

    .line 51
    .line 52
    .line 53
    iput-object v0, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->L$0:Ljava/lang/Object;

    .line 54
    .line 55
    iput-object v1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->L$1:Ljava/lang/Object;

    .line 56
    .line 57
    iput-object v6, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->L$2:Ljava/lang/Object;

    .line 58
    .line 59
    const/4 v0, 0x0

    .line 60
    iput v0, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->I$0:I

    .line 61
    .line 62
    iput v5, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->label:I

    .line 63
    .line 64
    invoke-interface {p1, v3, p0}, Lkotlinx/coroutines/flow/g;->collect(Lkotlinx/coroutines/flow/h;Lkotlin/coroutines/d;)Ljava/lang/Object;

    .line 65
    .line 66
    .line 67
    move-result-object p0

    .line 68
    if-ne p0, v2, :cond_5

    .line 69
    .line 70
    goto :goto_1

    .line 71
    :cond_3
    new-instance p1, Lin/swiggy/android/tejas/g;

    .line 72
    .line 73
    new-instance v3, Lin/swiggy/android/tejas/commons/error/r;

    .line 74
    .line 75
    invoke-virtual {v1}, Ljava/lang/Throwable;->getMessage()Ljava/lang/String;

    .line 76
    .line 77
    .line 78
    move-result-object v5

    .line 79
    if-nez v5, :cond_4

    .line 80
    .line 81
    const-string v5, "exception-transformer-"

    .line 82
    .line 83
    invoke-static {v5, v1}, Lin/swiggy/android/dagger/i3;->p(Ljava/lang/String;Ljava/lang/Throwable;)Ljava/lang/String;

    .line 84
    .line 85
    .line 86
    move-result-object v5

    .line 87
    :cond_4
    invoke-direct {v3, v5, v1}, Lin/swiggy/android/tejas/commons/error/r;-><init>(Ljava/lang/String;Ljava/lang/Throwable;)V

    .line 88
    .line 89
    .line 90
    const/16 v1, 0x1e

    .line 91
    .line 92
    invoke-direct {p1, v3, v6, v6, v1}, Lin/swiggy/android/tejas/g;-><init>(Lin/swiggy/android/tejas/commons/error/s;Ljava/lang/Integer;Ljava/lang/String;I)V

    .line 93
    .line 94
    .line 95
    iput-object v6, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->L$0:Ljava/lang/Object;

    .line 96
    .line 97
    iput-object v6, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->L$1:Ljava/lang/Object;

    .line 98
    .line 99
    iput-object v6, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->L$2:Ljava/lang/Object;

    .line 100
    .line 101
    iput v4, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$2;->label:I

    .line 102
    .line 103
    invoke-interface {v0, p1, p0}, Lkotlinx/coroutines/flow/h;->emit(Ljava/lang/Object;Lkotlin/coroutines/d;)Ljava/lang/Object;

    .line 104
    .line 105
    .line 106
    move-result-object p0

    .line 107
    if-ne p0, v2, :cond_5

    .line 108
    .line 109
    :goto_1
    return-object v2

    .line 110
    :cond_5
    :goto_2
    sget-object p0, Lkotlin/Unit;->a:Lkotlin/Unit;

    .line 111
    .line 112
    return-object p0
.end method
