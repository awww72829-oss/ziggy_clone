.class public final Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;
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
    c = "in.swiggy.android.tejas.ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1"
    f = "ResponseTransformerManager.kt"
    l = {
        0x24
    }
    m = "invokeSuspend"
    v = 0x1
.end annotation


# instance fields
.field final synthetic $this_transform:Lkotlinx/coroutines/flow/g;

.field private synthetic L$0:Ljava/lang/Object;

.field label:I


# direct methods
.method public constructor <init>(Lkotlinx/coroutines/flow/g;Lkotlin/coroutines/d;)V
    .locals 0

    iput-object p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;->$this_transform:Lkotlinx/coroutines/flow/g;

    const/4 p1, 0x2

    invoke-direct {p0, p1, p2}, Lkotlin/coroutines/jvm/internal/SuspendLambda;-><init>(ILkotlin/coroutines/d;)V

    return-void
.end method


# virtual methods
.method public final create(Ljava/lang/Object;Lkotlin/coroutines/d;)Lkotlin/coroutines/d;
    .locals 1

    new-instance v0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;

    iget-object p0, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;->$this_transform:Lkotlinx/coroutines/flow/g;

    invoke-direct {v0, p0, p2}, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;-><init>(Lkotlinx/coroutines/flow/g;Lkotlin/coroutines/d;)V

    iput-object p1, v0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;->L$0:Ljava/lang/Object;

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
    invoke-virtual {p0, p1, p2}, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;->create(Ljava/lang/Object;Lkotlin/coroutines/d;)Lkotlin/coroutines/d;

    .line 6
    .line 7
    .line 8
    move-result-object p0

    .line 9
    check-cast p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;

    .line 10
    .line 11
    sget-object p1, Lkotlin/Unit;->a:Lkotlin/Unit;

    .line 12
    .line 13
    invoke-virtual {p0, p1}, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;->invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;

    .line 14
    .line 15
    .line 16
    move-result-object p0

    .line 17
    return-object p0
.end method

.method public final invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;
    .locals 4

    .line 1
    sget-object v0, Lkotlin/coroutines/intrinsics/CoroutineSingletons;->COROUTINE_SUSPENDED:Lkotlin/coroutines/intrinsics/CoroutineSingletons;

    .line 2
    .line 3
    iget v1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;->label:I

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
    iget-object p0, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;->L$0:Ljava/lang/Object;

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
    iget-object p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;->L$0:Ljava/lang/Object;

    .line 29
    .line 30
    check-cast p1, Lkotlinx/coroutines/flow/h;

    .line 31
    .line 32
    iget-object v1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;->$this_transform:Lkotlinx/coroutines/flow/g;

    .line 33
    .line 34
    new-instance v3, Lin/swiggy/android/tejas/q;

    .line 35
    .line 36
    invoke-direct {v3, p1}, Lin/swiggy/android/tejas/q;-><init>(Lkotlinx/coroutines/flow/h;)V

    .line 37
    .line 38
    .line 39
    const/4 p1, 0x0

    .line 40
    iput-object p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;->L$0:Ljava/lang/Object;

    .line 41
    .line 42
    iput v2, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$lambda$0$$inlined$transform$1;->label:I

    .line 43
    .line 44
    invoke-interface {v1, v3, p0}, Lkotlinx/coroutines/flow/g;->collect(Lkotlinx/coroutines/flow/h;Lkotlin/coroutines/d;)Ljava/lang/Object;

    .line 45
    .line 46
    .line 47
    move-result-object p0

    .line 48
    if-ne p0, v0, :cond_2

    .line 49
    .line 50
    return-object v0

    .line 51
    :cond_2
    :goto_0
    sget-object p0, Lkotlin/Unit;->a:Lkotlin/Unit;

    .line 52
    .line 53
    return-object p0
.end method
