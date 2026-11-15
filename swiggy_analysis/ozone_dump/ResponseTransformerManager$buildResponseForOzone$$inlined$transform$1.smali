.class public final Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;
.super Lkotlin/coroutines/jvm/internal/SuspendLambda;
.source "SourceFile"

# interfaces
.implements Lkotlin/jvm/functions/Function2;


# annotations
.annotation system Ldalvik/annotation/Signature;
    value = {
        "Lkotlin/coroutines/jvm/internal/SuspendLambda;",
        "Lkotlin/jvm/functions/Function2<",
        "Lkotlinx/coroutines/flow/h;",
        "Lkotlin/coroutines/d<",
        "-",
        "Lkotlin/Unit;",
        ">;",
        "Ljava/lang/Object;",
        ">;"
    }
.end annotation

.annotation runtime Lkotlin/Metadata;
    d1 = {
        "\u0000\u000e\n\u0000\n\u0002\u0018\u0002\n\u0002\u0010\u0002\n\u0002\u0008\u0002\u0010\u0003\u001a\u00020\u0002\"\u0004\u0008\u0000\u0010\u0000*\u0008\u0012\u0004\u0012\u00028\u00000\u0001H\n\u00a2\u0006\u0004\u0008\u0003\u0010\u0004"
    }
    d2 = {
        "R",
        "Lkotlinx/coroutines/flow/h;",
        "",
        "<anonymous>",
        "(Lkotlinx/coroutines/flow/h;)V"
    }
    k = 0x3
    mv = {
        0x2,
        0x2,
        0x0
    }
.end annotation

.annotation runtime Lkotlin/coroutines/jvm/internal/c;
    c = "in.swiggy.android.tejas.ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1"
    f = "ResponseTransformerManager.kt"
    l = {
        0x24
    }
    m = "invokeSuspend"
    v = 0x1
.end annotation


# instance fields
.field final synthetic $errorChecker$inlined:Lin/swiggy/android/tejas/api/c;

.field final synthetic $errorTransformer$inlined:Lin/swiggy/android/tejas/coroutineUtils/b;

.field final synthetic $isSwiggyApi$inlined:Z

.field final synthetic $modelTransformer$inlined:Lin/swiggy/android/tejas/coroutineUtils/d;

.field final synthetic $this_transform:Lkotlinx/coroutines/flow/g;

.field private synthetic L$0:Ljava/lang/Object;

.field label:I


# direct methods
.method public constructor <init>(Lkotlinx/coroutines/flow/g;Lkotlin/coroutines/d;ZLin/swiggy/android/tejas/coroutineUtils/b;Lin/swiggy/android/tejas/api/c;Lin/swiggy/android/tejas/coroutineUtils/d;)V
    .locals 0

    iput-object p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$this_transform:Lkotlinx/coroutines/flow/g;

    iput-boolean p3, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$isSwiggyApi$inlined:Z

    iput-object p4, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$errorTransformer$inlined:Lin/swiggy/android/tejas/coroutineUtils/b;

    iput-object p5, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$errorChecker$inlined:Lin/swiggy/android/tejas/api/c;

    iput-object p6, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$modelTransformer$inlined:Lin/swiggy/android/tejas/coroutineUtils/d;

    const/4 p1, 0x2

    invoke-direct {p0, p1, p2}, Lkotlin/coroutines/jvm/internal/SuspendLambda;-><init>(ILkotlin/coroutines/d;)V

    return-void
.end method


# virtual methods
.method public final create(Ljava/lang/Object;Lkotlin/coroutines/d;)Lkotlin/coroutines/d;
    .locals 7

    new-instance v0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;

    iget-object v1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$this_transform:Lkotlinx/coroutines/flow/g;

    iget-boolean v3, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$isSwiggyApi$inlined:Z

    iget-object v4, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$errorTransformer$inlined:Lin/swiggy/android/tejas/coroutineUtils/b;

    iget-object v5, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$errorChecker$inlined:Lin/swiggy/android/tejas/api/c;

    iget-object v6, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$modelTransformer$inlined:Lin/swiggy/android/tejas/coroutineUtils/d;

    move-object v2, p2

    invoke-direct/range {v0 .. v6}, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;-><init>(Lkotlinx/coroutines/flow/g;Lkotlin/coroutines/d;ZLin/swiggy/android/tejas/coroutineUtils/b;Lin/swiggy/android/tejas/api/c;Lin/swiggy/android/tejas/coroutineUtils/d;)V

    iput-object p1, v0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->L$0:Ljava/lang/Object;

    return-object v0
.end method

.method public final invoke(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;
    .locals 0

    .line 1
    check-cast p1, Lkotlinx/coroutines/flow/h;

    .line 2
    .line 3
    check-cast p2, Lkotlin/coroutines/d;

    .line 4
    .line 5
    invoke-virtual {p0, p1, p2}, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->create(Ljava/lang/Object;Lkotlin/coroutines/d;)Lkotlin/coroutines/d;

    .line 6
    .line 7
    .line 8
    move-result-object p0

    .line 9
    check-cast p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;

    .line 10
    .line 11
    sget-object p1, Lkotlin/Unit;->a:Lkotlin/Unit;

    .line 12
    .line 13
    invoke-virtual {p0, p1}, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;

    .line 14
    .line 15
    .line 16
    move-result-object p0

    .line 17
    return-object p0
.end method

.method public final invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;
    .locals 9

    .line 1
    sget-object v0, Lkotlin/coroutines/intrinsics/CoroutineSingletons;->COROUTINE_SUSPENDED:Lkotlin/coroutines/intrinsics/CoroutineSingletons;

    .line 2
    .line 3
    iget v1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->label:I

    .line 4
    .line 5
    const/4 v2, 0x1

    .line 6
    if-eqz v1, :cond_1

    .line 7
    .line 8
    if-ne v1, v2, :cond_0

    .line 9
    .line 10
    iget-object p0, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->L$0:Ljava/lang/Object;

    .line 11
    .line 12
    check-cast p0, Lkotlinx/coroutines/flow/h;

    .line 13
    .line 14
    invoke-static {p1}, Lkotlin/l;->b(Ljava/lang/Object;)V

    .line 15
    .line 16
    .line 17
    goto :goto_0

    .line 18
    :cond_0
    const-string p0, "call to \'resume\' before \'invoke\' with coroutine"

    .line 19
    .line 20
    invoke-static {p0}, Lk;->e(Ljava/lang/String;)V

    .line 21
    .line 22
    .line 23
    const/4 p0, 0x0

    .line 24
    return-object p0

    .line 25
    :cond_1
    invoke-static {p1}, Lkotlin/l;->b(Ljava/lang/Object;)V

    .line 26
    .line 27
    .line 28
    iget-object p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->L$0:Ljava/lang/Object;

    .line 29
    .line 30
    move-object v4, p1

    .line 31
    check-cast v4, Lkotlinx/coroutines/flow/h;

    .line 32
    .line 33
    iget-object p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$this_transform:Lkotlinx/coroutines/flow/g;

    .line 34
    .line 35
    new-instance v3, Lin/swiggy/android/tejas/o;

    .line 36
    .line 37
    iget-boolean v5, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$isSwiggyApi$inlined:Z

    .line 38
    .line 39
    iget-object v6, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$errorTransformer$inlined:Lin/swiggy/android/tejas/coroutineUtils/b;

    .line 40
    .line 41
    iget-object v7, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$errorChecker$inlined:Lin/swiggy/android/tejas/api/c;

    .line 42
    .line 43
    iget-object v8, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->$modelTransformer$inlined:Lin/swiggy/android/tejas/coroutineUtils/d;

    .line 44
    .line 45
    invoke-direct/range {v3 .. v8}, Lin/swiggy/android/tejas/o;-><init>(Lkotlinx/coroutines/flow/h;ZLin/swiggy/android/tejas/coroutineUtils/b;Lin/swiggy/android/tejas/api/c;Lin/swiggy/android/tejas/coroutineUtils/d;)V

    .line 46
    .line 47
    .line 48
    const/4 v1, 0x0

    .line 49
    iput-object v1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->L$0:Ljava/lang/Object;

    .line 50
    .line 51
    iput v2, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1;->label:I

    .line 52
    .line 53
    invoke-interface {p1, v3, p0}, Lkotlinx/coroutines/flow/g;->collect(Lkotlinx/coroutines/flow/h;Lkotlin/coroutines/d;)Ljava/lang/Object;

    .line 54
    .line 55
    .line 56
    move-result-object p0

    .line 57
    if-ne p0, v0, :cond_2

    .line 58
    .line 59
    return-object v0

    .line 60
    :cond_2
    :goto_0
    sget-object p0, Lkotlin/Unit;->a:Lkotlin/Unit;

    .line 61
    .line 62
    return-object p0
.end method
